package monitoring

import (
	"context"
	"fmt"
	"time"
)

// Span represents a single operation
type Span interface {
	End()
}

// SimpleSpan just logs when an operation finished
type SimpleSpan struct {
	Name      string
	StartTime time.Time
}

func (s *SimpleSpan) End() {
	fmt.Printf("[TRACE] Finished: %s | Duration: %v\n", s.Name, time.Since(s.StartTime))
}

// Start creates a new span. In a real OTel setup, this would inject IDs into the context.
func Start(ctx context.Context, name string) (context.Context, Span) {
	fmt.Printf("[TRACE] Starting: %s\n", name)
	return ctx, &SimpleSpan{
		Name:      name,
		StartTime: time.Now(),
	}
}
