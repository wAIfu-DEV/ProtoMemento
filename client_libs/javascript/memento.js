"use strict";

const net = require("net");
const path = require("path");
const fs = require("fs");
const { ChildProcess, spawn } = require("child_process");
const { randomUUID } = require("crypto");

/** @typedef {{id: string, content: string, time: number, user: string? | undefined, score: number? | undefined, lifetime: number? | undefined}} MemObj */
/** @typedef {{memory: MemObj, dictance: number}} QueriedMemObj */

class Memory {
    /** @type {string} */ id;
    /** @type {string} */ content;
    /** @type {number} */ time;

    /** @type {string? | undefined} */ user;
    /** @type {number? | undefined} */ score;
    /** @type {number? | undefined} */ lifetime;

    /**
     *
     * @param {MemObj? | undefined} params
     */
    constructor(params = null) {
        if (params) {
            Object.assign(this, params);
        }
    }

    /**
     * @param {Record<string,any>} input
     * @returns {Memory}
     */
    static fromRecord(input) {
        return new Memory(input);
    }

    /**
     * @returns {MemObj}
     */
    toRecord() {
        let obj = {
            id: str(self.id),
            content: str(self.content),
            time: int(self.time),
        };
        if (this.user) obj["user"] = str(self.user);
        if (this.score) obj["score"] = float(self.score);
        if (this.lifetime) obj["lifetime"] = int(self.lifetime);
        return obj;
    }

    toJson() {
        return JSON.stringify(this.toRecord());
    }
};
exports.Memory = Memory

class QueriedMemory {
    /** @type {Memory} */ memory;
    /** @type {number} */ distance;

    /**
     *
     * @param {QueriedMemObj? | undefined} params
     */
    constructor(params = null) {
        if (params) {
            Object.assign(this, params);
        }
    }

    /**
     * @param {QueriedMemObj} input
     * @returns
     */
    static fromRecord(input) {
        return new QueriedMemory(input);
    }

    toRecord() {
        return {
            memory: this.memory.toRecord(),
            distance: Number(this.distance),
        };
    }

    toJson() {
        return JSON.stringify(this.toRecord());
    }
};
exports.QueriedMemory = QueriedMemory

class QueryResult {
    /** @type {QueriedMemory[]} */ shortTerm
    /** @type {QueriedMemory[]} */ longTerm
    /** @type {Memory[]} */        users
}
exports.QueryResult = QueryResult

class WSWrapper {
    constructor(url, options = {}) {
        this.url = url;
        this.websocket = null;
        this.listeners = new Map();

        // Options with sane defaults
        this.reconnectInterval = options.reconnectInterval || 2000; // ms
        this.maxRetries = options.maxRetries || Infinity;
        this.retryCount = 0;
        this.autoReconnect = options.autoReconnect !== false;

        this._connect();
    }

    _connect() {
        try {
            this.websocket = new WebSocket(this.url);

            this.websocket.onopen = (event) => {
                this.retryCount = 0;
                this._emit("open", event);
            };

            this.websocket.onmessage = (event) => {
                this._emit("message", event.data);
            };

            this.websocket.onerror = (event) => {
                this._emit("error", event);
            };

            this.websocket.onclose = (event) => {
                this._emit("close", event);

                if (this.autoReconnect && this.retryCount < this.maxRetries) {
                    setTimeout(() => {
                        this.retryCount++;
                        this._connect();
                    }, this.reconnectInterval);
                }
            };
        } catch (err) {
            this._emit("error", err);
        }
    }

    send(data) {
        if (this.websocket && this.websocket.readyState === WebSocket.OPEN) {
            this.websocket.send(data);
        } else {
            this._emit("error", new Error("WebSocket is not open"));
        }
    }

    close(code = 1000, reason = "Normal Closure") {
        this.autoReconnect = false;
        if (this.websocket) {
            this.websocket.close(code, reason);
        }
    }

    on(event, callback) {
        if (!this.listeners.has(event)) {
            this.listeners.set(event, []);
        }
        this.listeners.get(event).push(callback);
    }

    off(event, callback) {
        if (this.listeners.has(event)) {
            this.listeners.set(
                event,
                this.listeners.get(event).filter((cb) => cb !== callback)
            );
        }
    }

    _emit(event, data) {
        if (this.listeners.has(event)) {
            for (const callback of this.listeners.get(event)) {
                try {
                    callback(data);
                } catch (err) {
                    console.error("WSWrapper listener error:", err);
                }
            }
        }
    }
}

exports.Memento = class Memento {
    /** @private @type {URL} */ _url;
    /** @private @type {WSWrapper?} */ _conn;
    /** @private @type {ChildProcess} */ _proc;
    /** @private @type {string? | undefined} */ _abs_dir;

    /** @private @type {Record<string, (value: any)=>any>} */ _resolvers = {};

    /**
     * @param {{abs_dir?: string?, host: string, port: number}?} params
     */
    constructor(params = { abs_dir: null, host: "127.0.0.1", port: 4286 }) {
        this._conn = null;
        this._url = new URL(`wss://${params.host}:${params.port.toString()}`);
        this._abs_dir = params.abs_dir;
    }

    /**
     * @param {number} port
     * @param {string} host
     * @param {number} timeoutMs
     * @returns {Promise}
     */
    isPortOpen(port, host, timeoutMs = 2_000) {
        return new Promise((resolve) => {
            const socket = new net.Socket();

            socket.setTimeout(timeoutMs); // timeout in ms

            socket.once("connect", () => {
                socket.destroy();
                resolve(true); // something is listening
            });

            socket.once("timeout", () => {
                socket.destroy();
                resolve(false);
            });

            socket.once("error", () => {
                resolve(false); // connection refused or unreachable
            });

            socket.connect(port, host);
        });
    }

    async connect() {
        let isConnected = await this.isPortOpen(
            this._url.port,
            this._url.host,
            2_000
        );
        if (!isConnected) {
            if (!this._abs_path) {
                throw new Error(
                    "Memento instance is not open, and no abs_path have been provided to start a new one."
                );
            }

            pyPath = path.join(this._abs_dir, "venv", "Scripts", "python.exe");
            mainPath = path.join(this._abs_dir, "main.py");

            if (!fs.existsSync(pyPath) || !fs.existsSync(mainPath)) {
                throw new Error(
                    "abs_dir provided does not point to a valid Memento directory."
                );
            }

            this._proc = spawn(pyPath, [mainPath], {
                cwd: this._abs_dir,
            });
            process.once("exit", () => {
                this._proc.kill(2);
            });

            isConnected = await this.isPortOpen(
                this._url.port,
                this._url.host,
                10_000
            );
            if (!isConnected) {
                throw new Error("failed to run new Memento instance.");
            }
        }

        this._conn = new WSWrapper(this._url);
        this._conn.on("open", () => {
            this._conn.on("message", this._handleMessage);
        });
    }

    async _handleMessage(data) {
        try {
            var obj = JSON.parse(data);
        } catch (e) {
            return;
        }

        if (typeof obj["type"] != "string") {
            throw new Error(
                'received malformed payload from Memento. field: "type" is not of type string'
            );
        }

        if (typeof obj["uid"] != "string") {
            throw new Error(
                'received malformed payload from Memento. field: "uid" is not of type string'
            );
        }

        let msgType = obj["type"];
        let msgId = obj["uid"];

        switch (msgType) {
            case "query": {
                let res = new QueryResult()
                let dbs = obj["from"]
                
                if ("stm" in dbs)
                    for (let x of obj["stm"])
                        res.shortTerm.push(QueriedMemory.fromRecord(x))

                if ("ltm" in dbs)
                    for (let x of obj["ltm"])
                        res.longTerm.push(QueriedMemory.fromRecord(x))
                
                if ("users" in dbs)
                    for (let x of obj["users"])
                        res.users.push(Memory.fromRecord(x))
                
                if (msgId in this._resolvers) {
                    let resolver = this._resolvers[msgId]
                    resolver(res)
                } else {
                    throw new Error("received unhandled response to query request.")
                }
            }
        }
    }

    /**
     * @param {string} queryStr
     * @param params
     * @returns {Promise<QueryResult>}
     */
    async query(queryStr, params = {
        collectionName: "default",
        user: null,
        from: ["stm", "ltm", "users"],
        n: [1, 1, 1],
        timeoutMs: 5_000,
    }) {
        let reqId = randomUUID()

        let resolver = undefined
        let promise = new Promise((resolve) => {
            resolver = resolve
        })

        this._resolvers[reqId] = resolver

        this._conn.send(JSON.stringify({
            "uid": reqId,
            "type": "query",
            "query": queryStr,
            "ai_name": collectionName,
            "user": user,
            "from": from,
            "n": n,
        }))

        let timeoutPromise = new Promise((resolve) => setTimeout(resolve, params.timeoutMs))
        let result = await Promise.race([timeoutPromise, promise])

        delete this._resolvers[reqId]

        if (!result) {
            throw new Error("timeout")
        }
        return result
    }
};
