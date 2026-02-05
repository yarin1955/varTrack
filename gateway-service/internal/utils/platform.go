package utils

import (
	"context"
	pb_models "gateway-service/internal/gen/proto/go/vartrack/v1/models"
	"sync"
	"fmt"

)

type Platform interface {
	// EventTypeHeader returns the HTTP header key used by the provider for event types
	EventTypeHeader() string

	GetGitScmSignature() string

	// IsPushEvent checks if the given event type is a push event
	IsPushEvent(eventType string) bool

	// IsPREvent checks if the given event type is a pull request event
	IsPREvent(eventType string) bool

	// ConstructCloneURL generates the git clone URL
	ConstructCloneURL(repo string) string

	// CreateWebhook registers a webhook on the platform
	CreateWebhook(ctx context.Context, repoName string, endpoint string) error

	// Auth validates credentials against the platform
	Auth(ctx context.Context) error

	Open(ctx context.Context, config *pb_models.Platform) (Platform, error)
	Close(ctx context.Context) error

	// GetRepos returns a list of repos matching the glob patterns
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

type PlatformFactory struct {
}

// New creates a new database driver factory.
func New() *PlatformFactory {
	return &PlatformFactory{}
}

func (f *PlatformFactory) GetPlatform(ctx context.Context, config *pb_models.Platform) (Platform, error) {
	if config == nil {
		return nil, fmt.Errorf("platform config cannot be nil")
	}

	// Extract platform name from the config
	platformName := GetPlatformName(config)
	if platformName == "" {
		return nil, fmt.Errorf("platform name must be specified")
	}

	driver, err := Open(ctx, platformName, config)
	if err != nil {
		return nil, err
	}

	return driver, nil
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
