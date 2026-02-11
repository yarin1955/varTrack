package secret_managers

import (
	"context"
	"crypto/tls"
	"crypto/x509"
	"fmt"
	pb_models "gateway-service/internal/gen/proto/go/vartrack/v1/models"
	pb_vault "gateway-service/internal/gen/proto/go/vartrack/v1/models/secret_managers"

	"gateway-service/internal/utils"
	"net/http"
	"os"
	"time"

	vault "github.com/hashicorp/vault/api"
	"github.com/hashicorp/vault/api/auth/approle"
	authk8s "github.com/hashicorp/vault/api/auth/kubernetes"
	authuserpass "github.com/hashicorp/vault/api/auth/userpass"
)

var _ utils.SecretManager = (*Vault)(nil)

func init() {
	utils.RegisterSecretManager("vault", newVault)
}

type Vault struct {
	config *pb_vault.VaultConfig
	client *vault.Client
}

func newVault() utils.SecretManager {
	return &Vault{}
}

func (v *Vault) Open(ctx context.Context, config *pb_models.SecretManager) (utils.SecretManager, error) {
	vaultConfig := config.GetVault()
	if vaultConfig == nil {
		return nil, fmt.Errorf("vault driver: configuration is missing or not a Vault type")
	}

	v.config = vaultConfig

	client, err := v.buildClient(ctx)
	if err != nil {
		return nil, fmt.Errorf("vault driver: %w", err)
	}

	v.client = client
	return v, nil
}

// ────────────────────────────────────────────
// Client setup
// ────────────────────────────────────────────

func (v *Vault) buildClient(ctx context.Context) (*vault.Client, error) {
	cfg := vault.DefaultConfig()
	cfg.Address = v.config.Endpoint
	cfg.Timeout = time.Duration(v.config.GetTimeout()) * time.Second
	cfg.MaxRetries = int(v.config.GetMaxRetries())

	tlsConfig, err := v.buildTLSConfig()
	if err != nil {
		return nil, fmt.Errorf("failed to build TLS config: %w", err)
	}
	cfg.HttpClient = &http.Client{
		Transport: &http.Transport{
			TLSClientConfig: tlsConfig,
		},
	}

	client, err := vault.NewClient(cfg)
	if err != nil {
		return nil, fmt.Errorf("failed to create vault client: %w", err)
	}

	if ns := v.config.GetNamespace(); ns != "" {
		client.SetNamespace(ns)
	}

	if err := v.authenticate(ctx, client); err != nil {
		return nil, fmt.Errorf("authentication failed: %w", err)
	}

	return client, nil
}

func (v *Vault) buildTLSConfig() (*tls.Config, error) {
	tlsCfg := &tls.Config{
		InsecureSkipVerify: !v.config.GetVerifySsl(),
	}

	if ca := v.config.GetSslCa(); ca != "" {
		pool := x509.NewCertPool()
		if !pool.AppendCertsFromPEM([]byte(ca)) {
			return nil, fmt.Errorf("failed to parse vault CA certificate")
		}
		tlsCfg.RootCAs = pool
	}

	cert := v.config.GetSslCert()
	key := v.config.GetSslKey()
	if cert != "" && key != "" {
		keypair, err := tls.X509KeyPair([]byte(cert), []byte(key))
		if err != nil {
			return nil, fmt.Errorf("failed to load vault client certificate: %w", err)
		}
		tlsCfg.Certificates = []tls.Certificate{keypair}
	}

	return tlsCfg, nil
}

// ────────────────────────────────────────────
// Authentication
// ────────────────────────────────────────────

func (v *Vault) authenticate(ctx context.Context, client *vault.Client) error {
	switch auth := v.config.Auth.(type) {
	case *pb_vault.VaultConfig_TokenAuth:
		return v.authToken(client, auth.TokenAuth)
	case *pb_vault.VaultConfig_AppRoleAuth:
		return v.authAppRole(ctx, client, auth.AppRoleAuth)
	case *pb_vault.VaultConfig_KubernetesAuth:
		return v.authKubernetes(ctx, client, auth.KubernetesAuth)
	case *pb_vault.VaultConfig_UserpassAuth:
		return v.authUserPass(ctx, client, auth.UserpassAuth)
	default:
		return fmt.Errorf("unsupported vault auth type: %T", v.config.Auth)
	}
}

func (v *Vault) authToken(client *vault.Client, auth *pb_vault.TokenAuth) error {
	if auth.GetToken() == "" {
		return fmt.Errorf("vault token auth: token is empty")
	}
	client.SetToken(auth.GetToken())
	return nil
}

func (v *Vault) authAppRole(ctx context.Context, client *vault.Client, auth *pb_vault.AppRoleAuth) error {
	secretID := &approle.SecretID{}
	switch auth.GetSecretIdType() {
	case pb_vault.AppRoleAuth_PLAIN:
		secretID.FromString = auth.GetSecretId()
	case pb_vault.AppRoleAuth_ENVIRONMENT:
		secretID.FromEnv = auth.GetSecretId()
	default:
		return fmt.Errorf("unsupported approle secret_id_type: %v", auth.GetSecretIdType())
	}

	var opts []approle.LoginOption
	if mp := auth.GetMountPath(); mp != "" {
		opts = append(opts, approle.WithMountPath(mp))
	}

	appRoleAuth, err := approle.NewAppRoleAuth(auth.GetRoleId(), secretID, opts...)
	if err != nil {
		return fmt.Errorf("failed to create approle auth: %w", err)
	}

	resp, err := client.Auth().Login(ctx, appRoleAuth)
	if err != nil {
		return fmt.Errorf("failed to login with approle: %w", err)
	}
	if resp == nil || resp.Auth == nil {
		return fmt.Errorf("vault approle: empty auth response")
	}

	client.SetToken(resp.Auth.ClientToken)
	return nil
}

func (v *Vault) authKubernetes(ctx context.Context, client *vault.Client, auth *pb_vault.KubernetesAuth) error {
	jwtPath := auth.GetJwtPath()
	if jwtPath == "" {
		jwtPath = "/var/run/secrets/kubernetes.io/serviceaccount/token"
	}

	jwt, err := os.ReadFile(jwtPath)
	if err != nil {
		return fmt.Errorf("failed to read kubernetes JWT from %s: %w", jwtPath, err)
	}

	opts := []authk8s.LoginOption{
		authk8s.WithServiceAccountToken(string(jwt)),
	}
	if mp := auth.GetMountPath(); mp != "" {
		opts = append(opts, authk8s.WithMountPath(mp))
	}

	k8sAuth, err := authk8s.NewKubernetesAuth(auth.GetRole(), opts...)
	if err != nil {
		return fmt.Errorf("failed to create kubernetes auth: %w", err)
	}

	resp, err := client.Auth().Login(ctx, k8sAuth)
	if err != nil {
		return fmt.Errorf("failed to login with kubernetes: %w", err)
	}
	if resp == nil || resp.Auth == nil {
		return fmt.Errorf("vault kubernetes: empty auth response")
	}

	client.SetToken(resp.Auth.ClientToken)
	return nil
}

func (v *Vault) authUserPass(ctx context.Context, client *vault.Client, auth *pb_vault.UserPassAuth) error {
	var opts []authuserpass.LoginOption
	if mp := auth.GetMountPath(); mp != "" {
		opts = append(opts, authuserpass.WithMountPath(mp))
	}

	userpassAuth, err := authuserpass.NewUserpassAuth(
		auth.GetUsername(),
		&authuserpass.Password{FromString: auth.GetPassword()},
		opts...,
	)
	if err != nil {
		return fmt.Errorf("failed to create userpass auth: %w", err)
	}

	resp, err := client.Auth().Login(ctx, userpassAuth)
	if err != nil {
		return fmt.Errorf("failed to login with userpass: %w", err)
	}
	if resp == nil || resp.Auth == nil {
		return fmt.Errorf("vault userpass: empty auth response")
	}

	client.SetToken(resp.Auth.ClientToken)
	return nil
}

// ────────────────────────────────────────────
// Secret retrieval
// ────────────────────────────────────────────

func (v *Vault) GetSecret(ctx context.Context, path string, key string) (string, error) {
	mountPoint := v.config.GetMountPoint()

	var data map[string]interface{}

	switch v.config.GetKvVersion() {
	case 1:
		secret, err := v.client.Logical().ReadWithContext(ctx, fmt.Sprintf("%s/%s", mountPoint, path))
		if err != nil {
			return "", fmt.Errorf("failed to read KV v1 secret at %q: %w", path, err)
		}
		if secret == nil || secret.Data == nil {
			return "", fmt.Errorf("secret not found at %q", path)
		}
		data = secret.Data

	case 2:
		secret, err := v.client.KVv2(mountPoint).Get(ctx, path)
		if err != nil {
			return "", fmt.Errorf("failed to read KV v2 secret at %q: %w", path, err)
		}
		if secret == nil || secret.Data == nil {
			return "", fmt.Errorf("secret not found at %q", path)
		}
		data = secret.Data

	default:
		return "", fmt.Errorf("unsupported KV version: %d", v.config.GetKvVersion())
	}

	value, ok := data[key].(string)
	if !ok {
		return "", fmt.Errorf("key %q not found or not a string in secret %q", key, path)
	}

	return value, nil
}

// ────────────────────────────────────────────
// Lifecycle
// ────────────────────────────────────────────

func (v *Vault) Close(_ context.Context) error {
	if v.client != nil {
		v.client.ClearToken()
	}
	return nil
}