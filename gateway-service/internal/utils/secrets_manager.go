package utils

import (
	"context"
	"fmt"
	pb_models "gateway-service/internal/gen/proto/go/vartrack/v1/models"
	"sync"
)

// SecretManager defines the contract for secret management backends.
type SecretManager interface {
	// Open initializes the secret manager from protobuf config.
	Open(ctx context.Context, config *pb_models.SecretManager) (SecretManager, error)

	// GetSecret retrieves a secret value by path and key within the configured engine.
	GetSecret(ctx context.Context, path string, key string) (string, error)

	// Close cleans up connections.
	Close(ctx context.Context) error
}

// SecretManagerFunc is a constructor registered by each driver via init().
type SecretManagerFunc func() SecretManager

var (
	secretMgrMu       sync.RWMutex
	secretMgrRegistry = make(map[string]SecretManagerFunc)
)

// RegisterSecretManager registers a secret manager driver by name.
func RegisterSecretManager(name string, f SecretManagerFunc) {
	secretMgrMu.Lock()
	defer secretMgrMu.Unlock()
	if f == nil {
		panic("secret_manager: Register driver is nil")
	}
	if _, dup := secretMgrRegistry[name]; dup {
		panic(fmt.Sprintf("secret_manager: Register called twice for driver %s", name))
	}
	secretMgrRegistry[name] = f
}

// OpenSecretManager looks up the named driver and calls Open on it.
func OpenSecretManager(ctx context.Context, name string, config *pb_models.SecretManager) (SecretManager, error) {
	secretMgrMu.RLock()
	f, ok := secretMgrRegistry[name]
	secretMgrMu.RUnlock()

	if !ok {
		return nil, fmt.Errorf("secret_manager: unknown driver %q", name)
	}

	driver := f()
	return driver.Open(ctx, config)
}

// SecretManagerFactory creates secret manager instances from config.
type SecretManagerFactory struct{}

// NewSecretManagerFactory creates a new secret manager factory.
func NewSecretManagerFactory() *SecretManagerFactory {
	return &SecretManagerFactory{}
}

func (f *SecretManagerFactory) GetSecretManager(ctx context.Context, config *pb_models.SecretManager) (SecretManager, error) {
	if config == nil {
		return nil, fmt.Errorf("secret manager config cannot be nil")
	}

	name := GetSecretManagerName(config)
	if name == "" {
		return nil, fmt.Errorf("secret manager name must be specified")
	}

	return OpenSecretManager(ctx, name, config)
}

// GetSecretManagerName extracts the driver name from the oneof config.
func GetSecretManagerName(sm *pb_models.SecretManager) string {
	switch config := sm.Config.(type) {
	case *pb_models.SecretManager_Vault:
		return config.Vault.Name
	// case *pb_models.SecretManager_Gcp:
	//     return config.Gcp.Name
	// case *pb_models.SecretManager_Aws:
	//     return config.Aws.Name
	default:
		return ""
	}
}