package memento

// go get github.com/gorilla/websocket

import (
	"crypto/rand"
	"encoding/base64"
	"errors"
	"fmt"
	"math"
	"net/url"
	"os"
	"os/exec"
	"path"
	"sync"
	"time"

	websocket "github.com/gorilla/websocket"
)

type Memory struct {
	id      string
	content string
	time    int64

	user     *string
	score    *float64
	lifetime *int64
}

func (m *Memory) SetFromMap(obj map[string]any) error {
	var ok bool
	if m.id, ok = obj["id"].(string); !ok {
		return errors.New("missing field \"id\" from received memory object")
	}
	if m.content, ok = obj["content"].(string); !ok {
		return errors.New("missing field \"content\" from received memory object")
	}
	if fltTime, ok := obj["time"].(float64); ok {
		m.time = int64(math.Round(fltTime))
	} else {
		return errors.New("missing field \"time\" from received memory object")
	}

	if maybeUser, ok := obj["user"].(string); ok {
		m.user = &maybeUser
	}
	if maybeScore, ok := obj["score"].(float64); ok {
		m.score = &maybeScore
	}
	if maybeLifetime, ok := obj["lifetime"].(float64); ok {
		iVal := int64(math.Round(maybeLifetime))
		m.lifetime = &iVal
	}
	return nil
}

func (m *Memory) ToMap() map[string]any {
	var ret map[string]any = map[string]any{
		"id":      m.id,
		"content": m.content,
		"time":    m.time,
	}

	if m.user != nil {
		ret["user"] = *m.user
	}
	if m.score != nil {
		ret["score"] = *m.score
	}
	if m.lifetime != nil {
		ret["lifetime"] = *m.lifetime
	}
	return ret
}

type QueriedMemory struct {
	memory   Memory
	distance float64
}

func (q *QueriedMemory) SetFromMap(m map[string]any) error {
	memObj, ok := m["memory"].(map[string]any)
	if !ok {
		return errors.New("missing field \"memory\" from received queried memory object")
	}
	err := q.memory.SetFromMap(memObj)
	if err != nil {
		return err
	}
	if q.distance, ok = m["distance"].(float64); !ok {
		return errors.New("missing field \"distance\" from received queried memory object")
	}
	return nil
}

func (q *QueriedMemory) ToMap() map[string]any {
	return map[string]any{
		"memory":   q.memory.ToMap(),
		"distance": q.distance,
	}
}

type OpenLlmMessage struct {
	role    string
	content string
	name    *string
}

func (m *OpenLlmMessage) ToMap() map[string]any {
	ret := map[string]any{
		"role":    m.role,
		"content": m.content,
	}
	if m.name != nil {
		ret["name"] = *m.name
	}
	return ret
}

type QueryResult struct {
	Stm  []QueriedMemory
	Ltm  []QueriedMemory
	User []Memory
}

type CountResult struct {
	StmCount *int64
	LtmCount *int64
}

type genericResult[T any] struct {
	Result T
	Err    error
}

type messageHandlers struct {
	query map[string]chan genericResult[QueryResult]
	count map[string]chan genericResult[CountResult]
}

type Client struct {
	conn        *websocket.Conn
	backendProc *os.Process
	url         url.URL
	handlers    messageHandlers
	mutex       sync.Mutex
	connected   bool
}

func (c *Client) Disconnect(timeout time.Duration) {
	if c.conn != nil {
		c.mutex.Lock()
		c.connected = false
		c.mutex.Unlock()

		c.conn.WriteControl(websocket.CloseMessage, []byte{}, time.Now().Add(timeout))
		c.conn.Close()
	}
}

func (c *Client) handleMessage(jsonMsg map[string]any, msgType string, msgId string) {
	switch msgType {
	case "query":

		var msgHandler chan genericResult[QueryResult]
		{ // MUTEX CTX =========================================================
			c.mutex.Lock()
			defer c.mutex.Unlock()

			var ok bool
			msgHandler, ok = c.handlers.query[msgId]
			if !ok {
				fmt.Println("memento error: missing handler for query response")
				return
			}
			delete(c.handlers.query, msgId)
		}

		res := QueryResult{}

		if maybeStm, ok := jsonMsg["stm"].([]any); ok {
			for _, ent := range maybeStm {
				qm := QueriedMemory{}
				err := qm.SetFromMap(ent.(map[string]any))
				if err != nil {
					msgHandler <- genericResult[QueryResult]{Err: err}
					goto switch_query_end
				}
				res.Stm = append(res.Stm, qm)
			}
		}

		if maybeLtm, ok := jsonMsg["ltm"].([]any); ok {
			for _, ent := range maybeLtm {
				qm := QueriedMemory{}
				err := qm.SetFromMap(ent.(map[string]any))
				if err != nil {
					msgHandler <- genericResult[QueryResult]{Err: err}
					goto switch_query_end
				}
				res.Ltm = append(res.Ltm, qm)
			}
		}

		if maybeUsers, ok := jsonMsg["users"].([]any); ok {
			for _, ent := range maybeUsers {
				m := Memory{}
				err := m.SetFromMap(ent.(map[string]any))
				if err != nil {
					msgHandler <- genericResult[QueryResult]{Err: err}
					goto switch_query_end
				}
				res.User = append(res.User, m)
			}
		}

		msgHandler <- genericResult[QueryResult]{Result: res} // deliver result

	switch_query_end: // cleanup
		close(msgHandler)
		return
	case "count":

		var msgHandler chan genericResult[CountResult]
		{ // MUTEX CTX =========================================================
			c.mutex.Lock()
			defer c.mutex.Unlock()

			var ok bool
			msgHandler, ok = c.handlers.count[msgId]
			if !ok {
				fmt.Println("memento error: missing handler for count response")
				return
			}
			delete(c.handlers.count, msgId)
		}

		res := CountResult{}

		if maybeStm, ok := jsonMsg["stm"].(float64); ok {
			val := int64(math.Round(maybeStm))
			res.StmCount = &val
		}

		if maybeLtm, ok := jsonMsg["ltm"].(float64); ok {
			val := int64(math.Round(maybeLtm))
			res.LtmCount = &val
		}

		msgHandler <- genericResult[CountResult]{Result: res} // deliver result

		// cleanup
		close(msgHandler)
		return
	}
}

func (c *Client) recvLoop() {
	for {
		var jsonMsg map[string]any
		err := c.conn.ReadJSON(&jsonMsg)
		if err != nil {
			closeErr := &websocket.CloseError{}
			if errors.As(err, &closeErr) {
				c.mutex.Lock()
				c.connected = false
				c.mutex.Unlock()

				fmt.Printf("mement: connection closed with code: %d and message: %s", closeErr.Code, closeErr.Text)
				return // quit goroutine
			}

			fmt.Printf("memento error on recv: %s\n", err.Error())
			continue
		}

		msgType, ok := jsonMsg["type"].(string)
		if !ok {
			fmt.Println("memento error: missing field \"type\" in received json message")
			continue
		}

		msgId, ok := jsonMsg["uid"].(string)
		if !ok {
			fmt.Println("memento error: missing field \"uid\" in received json message")
			continue
		}

		c.handleMessage(jsonMsg, msgType, msgId)
	}
}

func NewClient(host string, port int, absPath string) (*Client, error) {
	c := &Client{}
	c.url = url.URL{Scheme: "ws", Host: fmt.Sprintf("%s:%d", host, port)}

	c.handlers = messageHandlers{
		query: map[string]chan genericResult[QueryResult]{},
		count: map[string]chan genericResult[CountResult]{},
	}

	c.backendProc = nil
	c.mutex = sync.Mutex{}

	conn, _, err := websocket.DefaultDialer.Dial(c.url.String(), nil)
	if err != nil {
		if absPath == "" {
			return nil, err
		} else {
			pythonPath := path.Join(absPath, "venv", "Scripts", "python.exe")
			mainPath := path.Join(absPath, "main.py")

			cmd := exec.Command(pythonPath, mainPath)
			err = cmd.Start()
			if err != nil {
				return nil, err
			}

			deadline := time.Now().Add(10 * time.Second)
			var lastErr error = nil

			for time.Now().Before(deadline) {
				conn, _, err = websocket.DefaultDialer.Dial(c.url.String(), nil)
				if err == nil {
					break
				}
				lastErr = err
				time.Sleep(500 * time.Millisecond)
			}

			if conn == nil {
				cmd.Process.Kill()
				return nil, lastErr
			}

			c.backendProc = cmd.Process
		}
	}

	c.conn = conn
	c.connected = true

	go c.recvLoop() // recv handler

	return c, nil
}

type DbEnum = string

const (
	DB_SHORT_TERM DbEnum = "stm"
	DB_LONG_TERM  DbEnum = "ltm"
	DB_USERS      DbEnum = "users"
)

func (c *Client) generateUid() string {
	randBytes := make([]byte, 16)
	rand.Read(randBytes)
	return base64.StdEncoding.EncodeToString(randBytes)
}

func (c *Client) isConnDead() bool {
	c.mutex.Lock()
	defer c.mutex.Unlock()
	return !c.connected
}

func (c *Client) Query(
	queryStr string,
	collectionName string,
	user *string,
	fromDb []DbEnum,
	n []int64,
	timeout time.Duration,
) (QueryResult, error) {

	var zero QueryResult
	var retErr error

	if c.isConnDead() {
		return zero, errors.New("memento: client not connected")
	}

	uniqueId := c.generateUid()

	resultChan := make(chan genericResult[QueryResult], 1)

	c.mutex.Lock() //===========================================================
	c.handlers.query[uniqueId] = resultChan
	c.mutex.Unlock() //=========================================================

	data := map[string]any{
		"uid":     uniqueId,
		"type":    "query",
		"query":   queryStr,
		"ai_name": collectionName,
		"from":    fromDb,
		"n":       n,
	}

	if user != nil {
		data["user"] = *user
	}

	err := c.conn.WriteJSON(data)
	if err != nil {
		retErr = err
		goto end_with_cleanup
	}

	select {
	case qRes := <-resultChan:
		return qRes.Result, qRes.Err
	case <-time.After(timeout):
		retErr = errors.New("timeout")
		goto end_with_cleanup
	}

end_with_cleanup:
	c.mutex.Lock() //===========================================================
	if ch, exists := c.handlers.query[uniqueId]; exists {
		delete(c.handlers.query, uniqueId)
		close(ch) // Safe to close since we still own it
	}
	c.mutex.Unlock() //=========================================================
	return zero, retErr
}

func (c *Client) Count(
	collectionName string,
	fromDb []DbEnum,
	timeout time.Duration,
) (CountResult, error) {

	var zero CountResult
	var retErr error

	if c.isConnDead() {
		return zero, errors.New("memento: client not connected")
	}

	uniqueId := c.generateUid()

	resultChan := make(chan genericResult[CountResult], 1)

	c.mutex.Lock() //===========================================================
	c.handlers.count[uniqueId] = resultChan
	c.mutex.Unlock() //=========================================================

	err := c.conn.WriteJSON(map[string]any{
		"uid":     uniqueId,
		"type":    "count",
		"ai_name": collectionName,
		"from":    fromDb,
	})
	if err != nil {
		retErr = err
		goto end_with_cleanup
	}

	select {
	case cRes := <-resultChan:
		return cRes.Result, cRes.Err
	case <-time.After(timeout):
		retErr = errors.New("timeout")
		goto end_with_cleanup
	}

end_with_cleanup:
	c.mutex.Lock() //===========================================================
	if ch, exists := c.handlers.count[uniqueId]; exists {
		delete(c.handlers.count, uniqueId)
		close(ch) // Safe to close since we still own it
	}
	c.mutex.Unlock() //=========================================================
	return zero, retErr
}

func (c *Client) Store(
	memories []Memory,
	collectionName string,
	to []DbEnum,
) error {
	if c.isConnDead() {
		return errors.New("memento: client not connected")
	}

	mems := []map[string]any{}
	for _, mem := range memories {
		mems = append(mems, mem.ToMap())
	}

	return c.conn.WriteJSON(map[string]any{
		"uid":      c.generateUid(),
		"type":     "store",
		"memories": mems,
		"ai_name":  collectionName,
		"to":       to,
	})
}

func (c *Client) Process(
	messages []OpenLlmMessage,
	context []OpenLlmMessage,
	collectionName string,
) error {
	if c.isConnDead() {
		return errors.New("memento: client not connected")
	}

	msgMaps := make([]map[string]any, len(messages))
	for i, msg := range messages {
		msgMaps[i] = msg.ToMap()
	}

	ctxMaps := make([]map[string]any, len(context))
	for i, msg := range context {
		ctxMaps[i] = msg.ToMap()
	}

	return c.conn.WriteJSON(map[string]any{
		"uid":      c.generateUid(),
		"type":     "process",
		"messages": msgMaps,
		"context":  ctxMaps,
		"ai_name":  collectionName,
	})
}

func (c *Client) CloseBackend() error {
	if c.isConnDead() {
		return errors.New("memento: client not connected")
	}

	return c.conn.WriteJSON(map[string]any{
		"uid":  c.generateUid(),
		"type": "close",
	})
}

func (c *Client) Evict(collectionName string) error {
	if c.isConnDead() {
		return errors.New("memento: client not connected")
	}

	return c.conn.WriteJSON(map[string]any{
		"uid":     c.generateUid(),
		"type":    "evict",
		"ai_name": collectionName,
	})
}

func (c *Client) Clear(
	collectionName string,
	user *string,
	target []DbEnum,
) error {
	if c.isConnDead() {
		return errors.New("memento: client not connected")
	}

	data := map[string]any{
		"uid":     c.generateUid(),
		"type":    "clear",
		"ai_name": collectionName,
		"target":  target,
	}
	if user != nil {
		data["user"] = *user
	}
	return c.conn.WriteJSON(data)
}
