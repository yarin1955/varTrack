package models

import (
	"context"
	"fmt"
	pb "gateway-service/internal/gen/proto/go/vartrack/v1/models"
	"gateway-service/internal/utils"
	"sync"
)

type Bundle struct {
	bundle               *pb.Bundle
	platformFactory      *utils.PlatformFactory
	secretManagerFactory *utils.SecretManagerFactory
	secretRefResolver    *utils.SecretRefResolver
	platforms            map[string]utils.Platform
	secretManagers       map[string]utils.SecretManager
	mu                   sync.RWMutex
}

func NewBundle(pbBundle *pb.Bundle) *Bundle {
	b := &Bundle{
		bundle:               pbBundle,
		platformFactory:      utils.New(),
		secretManagerFactory: utils.NewSecretManagerFactory(),
		platforms:            make(map[string]utils.Platform),
		secretManagers:       make(map[string]utils.SecretManager),
	}
	b.secretRefResolver = utils.NewSecretRefResolver(b.GetSecretManager)
	return b
}

// ────────────────────────────────────────────
// Rules
// ────────────────────────────────────────────

func (s *Bundle) FindRule(platformName, datasourceName string) *pb.Rule {
	for _, r := range s.bundle.Rules {
		if r.Platform == platformName && r.Datasource == datasourceName {
			return r
		}
	}
	return nil
}

func (s *Bundle) GetSecretManagerNameForRule(platformName, datasourceName string) string {
	rule := s.FindRule(platformName, datasourceName)
	if rule == nil {
		return ""
	}
	return rule.GetSecretManager()
}

// ────────────────────────────────────────────
// Platforms
// ────────────────────────────────────────────

func (s *Bundle) GetPlatform(ctx context.Context, name string, managerName string) (utils.Platform, error) {
	cacheKey := name
	if managerName != "" {
		cacheKey = name + ":" + managerName
	}

	s.mu.RLock()
	if plat, ok := s.platforms[cacheKey]; ok {
		s.mu.RUnlock()
		return plat, nil
	}
	s.mu.RUnlock()

	s.mu.Lock()
	defer s.mu.Unlock()

	if plat, ok := s.platforms[cacheKey]; ok {
		return plat, nil
	}

	var config *pb.Platform
	for _, p := range s.bundle.Platforms {
		if utils.GetPlatformName(p) == name {
			config = p
			break
		}
	}

	if config == nil {
		return nil, fmt.Errorf("platform %q not found in bundle configuration", name)
	}

	plat, err := s.platformFactory.GetPlatform(ctx, config, s.secretRefResolver, managerName)
	if err != nil {
		return nil, fmt.Errorf("failed to create platform %q: %w", name, err)
	}

	s.platforms[cacheKey] = plat
	return plat, nil
}

func (s *Bundle) GetPlatformForRule(ctx context.Context, platformName, datasourceName string) (utils.Platform, error) {
	managerName := s.GetSecretManagerNameForRule(platformName, datasourceName)
	return s.GetPlatform(ctx, platformName, managerName)
}

// ────────────────────────────────────────────
// Secret Managers
// ────────────────────────────────────────────

func (s *Bundle) GetSecretManager(ctx context.Context, name string) (utils.SecretManager, error) {
	s.mu.RLock()
	if sm, ok := s.secretManagers[name]; ok {
		s.mu.RUnlock()
		return sm, nil
	}
	s.mu.RUnlock()

	s.mu.Lock()
	defer s.mu.Unlock()

	if sm, ok := s.secretManagers[name]; ok {
		return sm, nil
	}

	var config *pb.SecretManager
	for _, sm := range s.bundle.SecretManagers {
		if utils.GetSecretManagerName(sm) == name {
			config = sm
			break
		}
	}

	if config == nil {
		return nil, fmt.Errorf("secret manager %q not found in bundle configuration", name)
	}

	sm, err := s.secretManagerFactory.GetSecretManager(ctx, config)
	if err != nil {
		return nil, fmt.Errorf("failed to create secret manager %q: %w", name, err)
	}

	s.secretManagers[name] = sm
	return sm, nil
}

// ────────────────────────────────────────────
// Lifecycle
// ────────────────────────────────────────────

func (s *Bundle) Close(ctx context.Context) error {
	s.mu.Lock()
	defer s.mu.Unlock()

	var errs []error
	for name, plat := range s.platforms {
		if err := plat.Close(ctx); err != nil {
			errs = append(errs, fmt.Errorf("failed to close platform %q: %w", name, err))
		}
	}
	for name, sm := range s.secretManagers {
		if err := sm.Close(ctx); err != nil {
			errs = append(errs, fmt.Errorf("failed to close secret manager %q: %w", name, err))
		}
	}

	if len(errs) > 0 {
		return fmt.Errorf("errors during close: %v", errs)
	}
	return nil
}

// ────────────────────────────────────────────
// Query helpers
// ────────────────────────────────────────────

func (s *Bundle) ListConfiguredPlatforms() []string {
	names := make([]string, 0, len(s.bundle.Platforms))
	for _, p := range s.bundle.Platforms {
		if n := utils.GetPlatformName(p); n != "" {
			names = append(names, n)
		}
	}
	return names
}

func (s *Bundle) ListConfiguredSecretManagers() []string {
	names := make([]string, 0, len(s.bundle.SecretManagers))
	for _, sm := range s.bundle.SecretManagers {
		if n := utils.GetSecretManagerName(sm); n != "" {
			names = append(names, n)
		}
	}
	return names
}

func (s *Bundle) GetBundle() *pb.Bundle {
	return s.bundle
}
