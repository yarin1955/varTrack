package models

import (
	"context"
	"fmt"
	pb_models "gateway-service/internal/gen/proto/go/vartrack/v1/models"
	"gateway-service/internal/utils"
)

type SecretManager interface {
	Open(ctx context.Context, config *pb_models.SecretManager) (SecretManager, error)
	GetSecret(ctx context.Context, path string, key string) (string, error)
	Close(ctx context.Context) error
}

var SecretManagerRegistry = utils.NewDriverRegistry[SecretManager, *pb_models.SecretManager](
	"secret_manager",
	func(driver SecretManager, ctx context.Context, config *pb_models.SecretManager) (SecretManager, error) {
		return driver.Open(ctx, config)
	},
)

var SecretManagerFactory = utils.NewDriverFactory(
	SecretManagerRegistry,
	func(c *pb_models.SecretManager) string {
		if c == nil {
			return ""
		}
		return GetSecretManagerName(c)
	},
	func(c *pb_models.SecretManager) error {
		if c == nil {
			return fmt.Errorf("secret manager config cannot be nil")
		}
		return nil
	},
	"secret_manager",
)

func GetSecretManagerName(sm *pb_models.SecretManager) string {
	switch config := sm.Config.(type) {
	case *pb_models.SecretManager_Vault:
		return config.Vault.Name
	default:
		return ""
	}
}