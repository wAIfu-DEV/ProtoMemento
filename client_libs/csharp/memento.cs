// Memento.cs

using System;
using System.Buffers;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.Net.WebSockets;
using System.Text;
using System.Text.Json;
using System.Text.Json.Serialization;
using System.Threading;
using System.Threading.Tasks;

namespace ProtoMemento
{
    public enum DbEnum { stm, ltm, users }

    public sealed class Memory
    {
        [JsonPropertyName("id")]       public string Id { get; set; } = Guid.NewGuid().ToString();
        [JsonPropertyName("content")]  public string Content { get; set; } = "";
        [JsonPropertyName("time")]     public long Time { get; set; } = DateTimeOffset.UtcNow.ToUnixTimeMilliseconds();

        [JsonPropertyName("user")]     public string? User { get; set; }
        [JsonPropertyName("score")]    public double? Score { get; set; }
        [JsonPropertyName("lifetime")] public int? Lifetime { get; set; }
    }

    public sealed class QueriedMemory
    {
        [JsonPropertyName("memory")]   public Memory Memory { get; set; } = new Memory();
        [JsonPropertyName("distance")] public double Distance { get; set; }
    }

    public sealed class OpenLlmMsg
    {
        [JsonPropertyName("role")]    public string Role { get; set; } = "user"; // "assistant" | "user" | "system"
        [JsonPropertyName("content")] public string Content { get; set; } = "";
        [JsonPropertyName("name")]    public string? Name { get; set; }
    }

    public sealed class QueryResult
    {
        public List<QueriedMemory> ShortTerm { get; set; } = new();
        public List<QueriedMemory> LongTerm  { get; set; } = new();
        public List<Memory> Users            { get; set; } = new();
    }

    internal sealed class Envelope
    {
        public string? type { get; set; }
        public string? uid  { get; set; }
    }

    internal sealed class QueryWireResp
    {
        public string type { get; set; } = "";
        public string uid { get; set; } = "";
        public List<string>? from { get; set; }
        public List<QueriedMemory>? stm { get; set; }
        public List<QueriedMemory>? ltm { get; set; }
        public List<Memory>? users { get; set; }
    }

    internal sealed class SummaryWireResp
    {
        public string type { get; set; } = "summary";
        public string uid { get; set; } = "";
        public string summary { get; set; } = "";
    }

    internal static class J
    {
        public static readonly JsonSerializerOptions Opts = new()
        {
            PropertyNamingPolicy = JsonNamingPolicy.CamelCase,
            DefaultIgnoreCondition = JsonIgnoreCondition.WhenWritingNull
        };
    }

    public sealed class MementoClient : IAsyncDisposable
    {
        private readonly Uri _uri;
        private readonly ClientWebSocket _ws = new();
        private readonly CancellationTokenSource _cts = new();
        private Task? _recvLoop;

        private readonly ConcurrentDictionary<string, TaskCompletionSource<QueryResult>> _pendingQueries = new();
        private readonly SemaphoreSlim _sendLock = new(1, 1);

        public event Action<string>? SummaryReceived;

        public MementoClient(string host = "127.0.0.1", int port = 4286, bool secure = false)
        {
            _uri = new Uri($"{(secure ? "wss" : "ws")}://{host}:{port}");
            _ws.Options.KeepAliveInterval = Timeout.Zero;
        }

        public async Task ConnectAsync(CancellationToken ct = default)
        {
            if (_ws.State == WebSocketState.Open) return;
            await _ws.ConnectAsync(_uri, ct).ConfigureAwait(false);
            _recvLoop = Task.Run(ReceiveLoopAsync);
        }

        public async ValueTask DisposeAsync()
        {
            _cts.Cancel();
            try
            {
                if (_ws.State == WebSocketState.Open)
                {
                    var payload = new { uid = Guid.NewGuid().ToString(), type = "close" };
                    await SendAsync(payload, CancellationToken.None);
                    await _ws.CloseAsync(WebSocketCloseStatus.NormalClosure, "client dispose", CancellationToken.None);
                }
            }
            catch { /* ignore */ }
            _ws.Dispose();
            _cts.Dispose();
            if (_recvLoop != null) await Task.WhenAny(_recvLoop, Task.Delay(50));
        }

        public async Task StoreAsync(
            List<Memory> memories,
            string collectionName = "default",
            List<DbEnum>? to = null,
            CancellationToken ct = default)
        {
            to ??= new List<DbEnum> { DbEnum.stm, DbEnum.users };
            var payload = new
            {
                uid = Guid.NewGuid().ToString(),
                type = "store",
                ai_name = collectionName,
                memories,
                to = MapDbEnums(to)
            };
            await SendAsync(payload, ct).ConfigureAwait(false);
        }

        public async Task<QueryResult> QueryAsync(
            string query,
            string collectionName = "default",
            string? user = null,
            List<DbEnum>? from = null,
            List<int>? n = null,
            TimeSpan? timeout = null,
            CancellationToken ct = default)
        {
            from ??= new List<DbEnum> { DbEnum.stm, DbEnum.ltm, DbEnum.users };
            n ??= new List<int> { 1, 1, 1 };

            var uid = Guid.NewGuid().ToString();
            var tcs = new TaskCompletionSource<QueryResult>(TaskCreationOptions.RunContinuationsAsynchronously);
            _pendingQueries[uid] = tcs;

            var payload = new
            {
                uid,
                type = "query",
                ai_name = collectionName,
                user = user ?? "",
                query,
                from = MapDbEnums(from),
                n
            };
			
			try
			{
				await SendAsync(payload, ct).ConfigureAwait(false);
			}
			catch
			{
				_pendingQueries.TryRemove(uid, out _);
				throw;
			}
			
            await SendAsync(payload, ct).ConfigureAwait(false);

            using var lcts = CancellationTokenSource.CreateLinkedTokenSource(_cts.Token, ct);
            var to = timeout ?? TimeSpan.FromSeconds(5);
            var finished = await Task.WhenAny(tcs.Task, Task.Delay(to, lcts.Token)).ConfigureAwait(false);
            _pendingQueries.TryRemove(uid, out _);
            if (finished != tcs.Task) throw new TimeoutException("Query timed out.");
            return await tcs.Task.ConfigureAwait(false);
        }

        public async Task ProcessAsync(
            List<OpenLlmMsg> messages,
            string collectionName = "default",
            List<OpenLlmMsg>? context = null,
            CancellationToken ct = default)
        {
            var payload = new
            {
                uid = Guid.NewGuid().ToString(),
                type = "process",
                ai_name = collectionName,
                context = context ?? new List<OpenLlmMsg>(),
                messages
            };
            await SendAsync(payload, ct).ConfigureAwait(false);
        }

        public async Task EvictAsync(string collectionName, CancellationToken ct = default)
        {
            var payload = new { uid = Guid.NewGuid().ToString(), type = "evict", ai_name = collectionName };
            await SendAsync(payload, ct).ConfigureAwait(false);
        }

        public async Task ClearAsync(string collectionName, string target /* "stm"|"ltm"|"users" */, string? user = null, CancellationToken ct = default)
        {
            var payload = new { uid = Guid.NewGuid().ToString(), type = "clear", ai_name = collectionName, target, user };
            await SendAsync(payload, ct).ConfigureAwait(false);
        }

        public async Task CountAsync(string collectionName, bool stm, bool ltm, CancellationToken ct = default)
        {
            var from = new List<string>();
            if (stm) from.Add("stm");
            if (ltm) from.Add("ltm");
            var payload = new { uid = Guid.NewGuid().ToString(), type = "count", ai_name = collectionName, from };
            await SendAsync(payload, ct).ConfigureAwait(false);
        }

        public async Task CloseAsync(CancellationToken ct = default)
        {
            if (_ws.State != WebSocketState.Open) return;
            var payload = new { uid = Guid.NewGuid().ToString(), type = "close" };
            await SendAsync(payload, ct).ConfigureAwait(false);
            await _ws.CloseAsync(WebSocketCloseStatus.NormalClosure, "client close", ct).ConfigureAwait(false);
        }

        private static List<string> MapDbEnums(List<DbEnum> xs)
        {
            var list = new List<string>(xs.Count);
            foreach (var e in xs) list.Add(e.ToString());
            return list;
        }

        private async Task SendAsync(object payload, CancellationToken ct)
        {
            var json = JsonSerializer.Serialize(payload, J.Opts);
            var bytes = Encoding.UTF8.GetBytes(json);
            await _sendLock.WaitAsync(ct).ConfigureAwait(false);
            try
            {
                await _ws.SendAsync(bytes, WebSocketMessageType.Text, endOfMessage: true, ct).ConfigureAwait(false);
            }
            finally
            {
                _sendLock.Release();
            }
        }

        private async Task ReceiveLoopAsync()
        {
            var buffer = ArrayPool<byte>.Shared.Rent(64 * 1024);
            try
            {
                while (!_cts.IsCancellationRequested && _ws.State == WebSocketState.Open)
                {
                    var builder = new ArrayBufferWriter<byte>();
                    WebSocketReceiveResult? res;
                    do
                    {
                        res = await _ws.ReceiveAsync(buffer, _cts.Token).ConfigureAwait(false);
                        if (res.MessageType == WebSocketMessageType.Close) return;
                        builder.Write(new ReadOnlySpan<byte>(buffer, 0, res.Count));
                    }
                    while (!res.EndOfMessage);

                    var raw = Encoding.UTF8.GetString(builder.WrittenSpan);
                    HandleIncoming(raw);
                }
            }
            catch { }
            finally
            {
                ArrayPool<byte>.Shared.Return(buffer);
            }
        }

        private void HandleIncoming(string raw)
        {
            Envelope? env = null;
            try { env = JsonSerializer.Deserialize<Envelope>(raw, J.Opts); } catch { }
            if (env?.type is null) return;

            switch (env.type)
            {
                case "query":
                {
                    var wire = JsonSerializer.Deserialize<QueryWireResp>(raw, J.Opts);
                    if (wire == null) return;

                    var qr = new QueryResult
                    {
                        ShortTerm = wire.stm ?? new(),
                        LongTerm  = wire.ltm ?? new(),
                        Users     = wire.users ?? new()
                    };

                    if (env.uid != null && _pendingQueries.TryGetValue(env.uid, out var tcs))
                        tcs.TrySetResult(qr);
                    break;
                }
                case "summary":
                {
                    var s = JsonSerializer.Deserialize<SummaryWireResp>(raw, J.Opts);
                    if (s == null) return;
                    SummaryReceived?.Invoke(s.summary ?? "");
                    break;
                }
                case "error":
                {
                    if (env.uid != null && _pendingQueries.TryGetValue(env.uid, out var tcs))
                        tcs.TrySetException(new InvalidOperationException(raw));
                    break;
                }
                default:
                    break;
            }
        }
    }
}