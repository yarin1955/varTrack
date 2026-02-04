package utils

import (
	"context"
	"fmt"
	pb_models "gateway-service/internal/gen/proto/go/vartrack/v1/models"
	"sync"
)

type PlatformFunc func() Platform

var (
	platformsMu sync.RWMutex
	platforms   = make(map[string]PlatformFunc)
)

func Register(name string, f PlatformFunc) {
	platformsMu.Lock()
	defer platformsMu.Unlock()
	if f == nil {
		panic("platform: Register driver is nil")
	}
	if _, dup := platforms[name]; dup {
		panic(fmt.Sprintf("platform: Register called twice for driver %s", name))
	}
	platforms[name] = f
}

func Open(ctx context.Context, name string, config *pb_models.Platform) (Platform, error) {
	platformsMu.RLock()
	f, ok := platforms[name]
	platformsMu.RUnlock()

	if !ok {
		return nil, fmt.Errorf("platform: unknown driver %q", name)
	}

	driver := f()
	return driver.Open(ctx, config)
}

func GetPlatformName(p *pb_models.Platform) string {
	switch config := p.Config.(type) {
	case *pb_models.Platform_Github:
		return config.Github.Name
	// Add other platforms when you implement them
	// case *pb_models.Platform_Gitlab:
	//     return config.Gitlab.Name
	// case *pb_models.Platform_Bitbucket:
	//     return config.Bitbucket.Name
	default:
		return ""
	}
}
