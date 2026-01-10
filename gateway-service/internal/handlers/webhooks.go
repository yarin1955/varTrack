package handlers

import (
	"net/http"
)

type WebhookHandler struct{}

func NewWebhookHandler() *WebhookHandler {
	return &WebhookHandler{}
}

func (h *WebhookHandler) Handle(w http.ResponseWriter, r *http.Request) {
	w.Write([]byte("hello world"))
}
