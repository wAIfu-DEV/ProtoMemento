package memento

// go get github.com/gorilla/websocket

import (
	"crypto/rand"
	"encoding/base64"
	"errors"
	"fmt"
	"net/url"
	"time"

	websocket "github.com/gorilla/websocket"
)

type Memory struct {
	id      string
	content string
	time    int64

	user     *string
	score    *float32
	lifetime *int32
}

func (m *Memory) SetFromMap(obj map[string]any) error {
	var ok bool
	if m.id, ok = obj["id"].(string); !ok {
		return errors.New("missing field \"id\" from received memory object")
	}
	if m.content, ok = obj["content"].(string); !ok {
		return errors.New("missing field \"content\" from received memory object")
	}
	if m.time, ok = obj["time"].(int64); !ok {
		return errors.New("missing field \"time\" from received memory object")
	}

	if maybeUser, ok := obj["user"].(string); ok {
		m.user = &maybeUser
	}
	if maybeScore, ok := obj["score"].(float32); ok {
		m.score = &maybeScore
	}
	if maybeLifetime, ok := obj["lifetime"].(int32); ok {
		m.lifetime = &maybeLifetime
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
	distance float32
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
	if q.distance, ok = m["distance"].(float32); !ok {
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

type messageHandlers struct {
	query map[string]chan QueryResult
	count map[string]chan CountResult
}

type Client struct {
	conn     *websocket.Conn
	url      url.URL
	errChan  chan error
	done     chan bool
	handlers messageHandlers
}

func (c *Client) Disconnect(timeout time.Duration) {
	if c.conn != nil {
		c.conn.WriteControl(websocket.CloseMessage, []byte{}, time.Now().Add(timeout))
		c.conn.Close()
	}
}

func (c *Client) handleMessage(jsonMsg map[string]any, msgType string, msgId string) {
	switch msgType {
	case "query":
		msgHandler, ok := c.handlers.query[msgId]
		if !ok {
			c.errChan <- errors.New("missing handler for query response")
			return
		}
		res := QueryResult{}

		if maybeStm, ok := jsonMsg["stm"].([]map[string]any); ok {
			for _, ent := range maybeStm {
				qm := QueriedMemory{}
				err := qm.SetFromMap(ent)
				if err != nil {
					c.errChan <- err
					goto switch_query_end
				}
				res.Stm = append(res.Stm, qm)
			}
		}

		if maybeLtm, ok := jsonMsg["ltm"].([]map[string]any); ok {
			for _, ent := range maybeLtm {
				qm := QueriedMemory{}
				err := qm.SetFromMap(ent)
				if err != nil {
					c.errChan <- err
					goto switch_query_end
				}
				res.Ltm = append(res.Ltm, qm)
			}
		}

		if maybeUsers, ok := jsonMsg["users"].([]map[string]any); ok {
			for _, ent := range maybeUsers {
				m := Memory{}
				err := m.SetFromMap(ent)
				if err != nil {
					c.errChan <- err
					goto switch_query_end
				}
				res.User = append(res.User, m)
			}
		}

		msgHandler <- res // deliver result

	switch_query_end: // cleanup
		close(msgHandler)
		delete(c.handlers.query, msgId)
		return
	case "count":
		msgHandler, ok := c.handlers.count[msgId]
		if !ok {
			c.errChan <- errors.New("missing handler for count response")
			return
		}
		res := CountResult{}

		if maybeStm, ok := jsonMsg["stm"].(int64); ok {
			res.StmCount = &maybeStm
		}

		if maybeLtm, ok := jsonMsg["ltm"].(int64); ok {
			res.LtmCount = &maybeLtm
		}

		msgHandler <- res // deliver result

		// cleanup
		close(msgHandler)
		delete(c.handlers.count, msgId)
		return
	}
}

func (c *Client) recvLoop() {
	defer close(c.done)
	defer close(c.errChan)

	for {
		var jsonMsg map[string]any
		err := c.conn.ReadJSON(&jsonMsg)
		if err != nil {
			c.errChan <- err
			maybeCloseErr := &websocket.CloseError{}
			if errors.As(err, &maybeCloseErr) {
				return // quit goroutine
			}
			continue
		}

		msgType, ok := jsonMsg["type"].(string)
		if !ok {
			c.errChan <- errors.New("missing field \"type\" in json message")
			continue
		}

		msgId, ok := jsonMsg["uid"].(string)
		if !ok {
			c.errChan <- errors.New("missing field \"uid\" in json message")
			continue
		}

		c.handleMessage(jsonMsg, msgType, msgId)
	}
}

func NewClient(host string, port int) (*Client, error) {
	c := &Client{}
	c.url = url.URL{Scheme: "ws", Host: fmt.Sprintf("%s:%d", host, port)}

	c.handlers = messageHandlers{
		query: map[string]chan QueryResult{},
		count: map[string]chan CountResult{},
	}

	conn, _, err := websocket.DefaultDialer.Dial(c.url.String(), nil)
	if err != nil {
		return nil, err
	}

	c.conn = conn
	c.done = make(chan bool, 1)
	c.errChan = make(chan error)

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

func (c *Client) Query(
	queryStr string,
	collectionName string,
	user *string,
	fromDb []DbEnum,
	n []int64,
	timeout time.Duration,
) (QueryResult, error) {

	var zero QueryResult

	uniqueId := c.generateUid()

	resultChan := make(chan QueryResult)
	c.handlers.query[uniqueId] = resultChan

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
		return zero, err
	}

	select {
	case qRes := <-resultChan:
		return qRes, nil
	case <-time.After(timeout):
		return zero, errors.New("timeout")
	}
}

func (c *Client) Count(
	collectionName string,
	fromDb []DbEnum,
	timeout time.Duration,
) (CountResult, error) {

	var zero CountResult

	uniqueId := c.generateUid()

	resultChan := make(chan CountResult)
	c.handlers.count[uniqueId] = resultChan

	err := c.conn.WriteJSON(map[string]any{
		"uid":     uniqueId,
		"type":    "count",
		"ai_name": collectionName,
		"from":    fromDb,
	})
	if err != nil {
		return zero, err
	}

	select {
	case cRes := <-resultChan:
		return cRes, nil
	case <-time.After(timeout):
		return zero, errors.New("timeout")
	}
}

func (c *Client) Store(
	memories []Memory,
	collectionName string,
	to []DbEnum,
) error {
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
	msgMaps := make([]map[string]any, len(messages))
	for _, msg := range messages {
		msgMaps = append(msgMaps, msg.ToMap())
	}

	ctxMaps := make([]map[string]any, len(context))
	for _, msg := range context {
		ctxMaps = append(ctxMaps, msg.ToMap())
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
	return c.conn.WriteJSON(map[string]any{
		"uid":  c.generateUid(),
		"type": "close",
	})
}

func (c *Client) Evict(collectionName string) error {
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
