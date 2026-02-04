package secrets_managers

import (
	"context"
	"fmt"
	pb_vault "gateway-service/internal/gen/proto/go/vartrack/v1/models/secrets_managers"
	"gateway-service/internal/utils"
	vault "github.com/hashicorp/vault/api"
	"time"
)

type HashicorpVault struct {
	cfg    *pb_vault.VaultConfig
	client *vault.Client
}

func init() {
	// Clean registration using the proto-defined name.
	utils.SecretsRegistry.Register(&pb_vault.VaultConfig{}, NewVault)
}

func NewVault(config any) (utils.ISecretsManager, error) {
	cfg := config.(*pb_vault.VaultConfig)

	vConfig := vault.DefaultConfig()
	vConfig.Address = cfg.Endpoint
	vConfig.Timeout = time.Duration(cfg.Timeout) * time.Second

	// Handle SSL configuration
	if err := vConfig.ConfigureTLS(&vault.TLSConfig{
		Insecure: !cfg.VerifySsl,
		CACert:   cfg.GetCaCertPath(),
	}); err != nil {
		return nil, fmt.Errorf("failed to configure vault TLS: %w", err)
	}

	client, err := vault.NewClient(vConfig)
	if err != nil {
		return nil, fmt.Errorf("failed to create vault client: %w", err)
	}

	if cfg.Namespace != "" {
		client.SetNamespace(cfg.Namespace)
	}

	return &HashicorpVault{cfg: cfg, client: client}, nil
}

func (v *HashicorpVault) Auth() error {
	switch v.cfg.AuthMethod {
	case "token":
		if v.cfg.GetToken() == "" {
			return fmt.Errorf("token auth selected but no token provided")
		}
		v.client.SetToken(v.cfg.GetToken())
		return nil

	case "approle":
		roleID := v.cfg.GetRoleId()
		secretID := v.cfg.GetSecretId()

		data := map[string]interface{}{
			"role_id":   roleID,
			"secret_id": secretID,
		}

		resp, err := v.client.Logical().Write("auth/approle/login", data)
		if err != nil {
			return fmt.Errorf("approle login failed: %w", err)
		}

		v.client.SetToken(resp.Auth.ClientToken)
		return nil

	default:
		return fmt.Errorf("auth method %s not yet implemented", v.cfg.AuthMethod)
	}
}

func (v *HashicorpVault) GetSecret(ctx context.Context, secretPath string) (map[string]interface{}, error) {
	// Vault KV V2 puts data under the 'data/' prefix in the path
	finalPath := secretPath
	if v.cfg.KvVersion == 2 {
		finalPath = fmt.Sprintf("%s/data/%s", v.cfg.MountPoint, secretPath)
	} else {
		finalPath = fmt.Sprintf("%s/%s", v.cfg.MountPoint, secretPath)
	}

	secret, err := v.client.Logical().ReadWithContext(ctx, finalPath)
	if err != nil {
		return nil, fmt.Errorf("failed to read secret at %s: %w", finalPath, err)
	}

	if secret == nil || secret.Data == nil {
		return nil, fmt.Errorf("no secret found at path: %s", finalPath)
	}

	// KV V2 nests the actual values inside a "data" map
	if v.cfg.KvVersion == 2 {
		if data, ok := secret.Data["data"].(map[string]interface{}); ok {
			return data, nil
		}
	}

	return secret.Data, nil
}

func (v *HashicorpVault) Close() {
	// The standard Vault client doesn't require explicit closing of connections,
	// but we could clear the token for security.
	v.client.SetToken("")
}
