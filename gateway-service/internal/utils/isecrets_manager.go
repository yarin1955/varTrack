package utils

import (
	"context"
)

// ISecretsManager defines the contract for secrets management backends.
type ISecretsManager interface {
	// Auth performs authentication with the secrets manager.
	Auth() error
	// GetSecret retrieves a secret map from the specified path.
	GetSecret(ctx context.Context, path string) (map[string]interface{}, error)
	// Close cleans up connections.
	Close()
}
