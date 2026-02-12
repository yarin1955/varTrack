package models

import (
	"context"
	"fmt"
	pb_models "gateway-service/internal/gen/proto/go/vartrack/v1/models"
	"gateway-service/internal/utils"
	"sync"
)

type Platform interface {
	EventTypeHeader() string
	GetGitScmSignature() string
	IsPushEvent(eventType string) bool
	IsPREvent(eventType string) bool
	VerifyWebhook(payload []byte, signatureHeader string) bool
	ConstructCloneURL(repo string) string
	Auth(ctx context.Context) error
	Open(ctx context.Context, config *pb_models.Platform, resolver *utils.SecretRefResolver, managerName string) (Platform, error)
	Close(ctx context.Context) error
	GetRepos(ctx context.Context, patterns []string) ([]string, error)
	GetSecret() string
}

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

func Open(ctx context.Context, name string, config *pb_models.Platform, resolver *utils.SecretRefResolver, managerName string) (Platform, error) {
	platformsMu.RLock()
	f, ok := platforms[name]
	platformsMu.RUnlock()

	if !ok {
		return nil, fmt.Errorf("platform: unknown driver %q", name)
	}

	driver := f()
	return driver.Open(ctx, config, resolver, managerName)
}

type PlatformFactory struct{}

func New() *PlatformFactory {
	return &PlatformFactory{}
}

func (f *PlatformFactory) GetPlatform(ctx context.Context, config *pb_models.Platform, resolver *utils.SecretRefResolver, managerName string) (Platform, error) {
	if config == nil {
		return nil, fmt.Errorf("platform config cannot be nil")
	}

	platformName := GetPlatformName(config)
	if platformName == "" {
		return nil, fmt.Errorf("platform name must be specified")
	}

	return Open(ctx, platformName, config, resolver, managerName)
}

func GetPlatformName(p *pb_models.Platform) string {
	switch config := p.Config.(type) {
	case *pb_models.Platform_Github:
		return config.Github.Name
	default:
		return ""
	}
}
