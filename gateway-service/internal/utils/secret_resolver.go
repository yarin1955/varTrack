package utils

import (
	"context"
	"fmt"
	pb_utils "gateway-service/internal/gen/proto/go/vartrack/v1/utils"
)

// SecretRefResolver resolves SecretRef values — either returning the inline
// value or fetching from the secret manager provided at call time.
type SecretRefResolver struct {
	getManager func(ctx context.Context, name string) (SecretManager, error)
}

func NewSecretRefResolver(getManager func(ctx context.Context, name string) (SecretManager, error)) *SecretRefResolver {
	return &SecretRefResolver{getManager: getManager}
}

// Resolve returns the plain-text value for a SecretRef.
//   - If ref is nil, returns empty string.
//   - If ref is an inline value, returns it directly.
//   - If ref is an external reference, uses managerName to fetch.
func (r *SecretRefResolver) Resolve(ctx context.Context, ref *pb_utils.SecretRef, managerName string) (string, error) {
	if ref == nil {
		return "", nil
	}

	switch source := ref.Source.(type) {
	case *pb_utils.SecretRef_Value:
		return source.Value, nil

	case *pb_utils.SecretRef_Ref:
		extRef := source.Ref
		if extRef.Path == "" || extRef.Key == "" {
			return "", fmt.Errorf("external secret ref: path and key are required")
		}

		if managerName == "" {
			return "", fmt.Errorf(
				"secret ref (path=%q, key=%q) requires a secret_manager but none is configured in the rule",
				extRef.Path, extRef.Key,
			)
		}

		sm, err := r.getManager(ctx, managerName)
		if err != nil {
			return "", fmt.Errorf("failed to get secret manager %q: %w", managerName, err)
		}

		value, err := sm.GetSecret(ctx, extRef.Path, extRef.Key)
		if err != nil {
			return "", fmt.Errorf(
				"failed to resolve secret (manager=%s, path=%s, key=%s): %w",
				managerName, extRef.Path, extRef.Key, err,
			)
		}

		return value, nil

	default:
		return "", fmt.Errorf("secret ref has no source set")
	}
}
