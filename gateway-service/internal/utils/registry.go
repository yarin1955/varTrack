package utils

import (
	"context"
	"fmt"
	"sync"
)

// DriverRegistry is a generic, thread-safe registry for drivers that follow
// the Open pattern (e.g. platforms, secret managers).
type DriverRegistry[D any, C any] struct {
	mu       sync.RWMutex
	drivers  map[string]func() D
	opener   func(driver D, ctx context.Context, config C) (D, error)
	typeName string
}

func NewDriverRegistry[D any, C any](
	typeName string,
	opener func(driver D, ctx context.Context, config C) (D, error),
) *DriverRegistry[D, C] {
	return &DriverRegistry[D, C]{
		drivers:  make(map[string]func() D),
		opener:   opener,
		typeName: typeName,
	}
}

func (r *DriverRegistry[D, C]) Register(name string, f func() D) {
	r.mu.Lock()
	defer r.mu.Unlock()
	if f == nil {
		panic(fmt.Sprintf("%s: Register driver is nil", r.typeName))
	}
	if _, dup := r.drivers[name]; dup {
		panic(fmt.Sprintf("%s: Register called twice for driver %s", r.typeName, name))
	}
	r.drivers[name] = f
}

func (r *DriverRegistry[D, C]) Open(ctx context.Context, name string, config C) (D, error) {
	r.mu.RLock()
	f, ok := r.drivers[name]
	r.mu.RUnlock()

	var zero D
	if !ok {
		return zero, fmt.Errorf("%s: unknown driver %q", r.typeName, name)
	}

	driver := f()
	return r.opener(driver, ctx, config)
}
