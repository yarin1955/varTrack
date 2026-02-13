package middlewares

import (
	"fmt"
	"log/slog"
	"math"
	"net"
	"net/http"
	"strings"
	"sync"
	"time"

	"golang.org/x/time/rate"
)

// pattern — a single struct that controls both global and per-key limits.
type RateLimiterConfig struct {
	// Global token-bucket — protects the service as a whole.
	// BucketQPS = math.MaxFloat64 effectively disables global limiting.
	BucketQPS  float64
	BucketSize int

	// Per-IP exponential back-off — slows down individual abusers.
	// CoolDown = 0 disables per-IP limiting entirely.
	BaseDelay     time.Duration
	MaxDelay      time.Duration
	CoolDown      time.Duration
	BackoffFactor float64

	// CleanupInterval controls how often stale per-IP entries are reaped.
	CleanupInterval time.Duration
}

// DefaultRateLimiterConfig returns production-ready defaults.
//
//	Global:  100 req/s, burst 200.
//	Per-IP:  1 s base delay, 60 s max, 2 min cool-down, ×2 backoff.
func DefaultRateLimiterConfig() RateLimiterConfig {
	return RateLimiterConfig{
		BucketQPS:       100,
		BucketSize:      200,
		BaseDelay:       time.Second,
		MaxDelay:        60 * time.Second,
		CoolDown:        2 * time.Minute,
		BackoffFactor:   2.0,
		CleanupInterval: 5 * time.Minute,
	}
}

// RateLimiter combines a global token-bucket with per-IP exponential
// back-off that auto-resets after a cool-down period.
type RateLimiter struct {
	global  *rate.Limiter
	cfg     RateLimiterConfig
	mu      sync.Mutex
	perIP   map[string]*ipState
	closeCh chan struct{}
}

type ipState struct {
	failures    int
	lastSeen    time.Time
	blockedUtil time.Time
}

// NewRateLimiter creates a limiter from the given config.
func NewRateLimiter(cfg RateLimiterConfig) *RateLimiter {
	rl := &RateLimiter{
		global:  rate.NewLimiter(rate.Limit(cfg.BucketQPS), cfg.BucketSize),
		cfg:     cfg,
		perIP:   make(map[string]*ipState),
		closeCh: make(chan struct{}),
	}

	if cfg.CleanupInterval > 0 {
		go rl.cleanup()
	}
	return rl
}

// Middleware wraps an http.Handler with combined global + per-IP limiting.
func (rl *RateLimiter) Middleware(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		// 1. Global bucket — fast path, no per-key state.
		if !rl.global.Allow() {
			slog.Warn("rate limit: global bucket exhausted")
			http.Error(w, "Too Many Requests", http.StatusTooManyRequests)
			return
		}

		// 2. Per-IP back-off (skip if cool-down disabled).
		if rl.cfg.CoolDown > 0 {
			ip := extractIP(r)
			if wait := rl.perIPDelay(ip); wait > 0 {
				slog.Warn("rate limit: per-IP backoff",
					"ip", ip,
					"retry_after_ms", wait.Milliseconds(),
				)
				w.Header().Set("Retry-After", fmt.Sprintf("%.0f", math.Ceil(wait.Seconds())))
				http.Error(w, "Too Many Requests", http.StatusTooManyRequests)
				return
			}
		}

		next.ServeHTTP(w, r)
	})
}

// Close stops the background cleanup goroutine.
func (rl *RateLimiter) Close() {
	close(rl.closeCh)
}

// perIPDelay returns how long the caller must wait before the next
// request is allowed. Zero means the request may proceed immediately.
//
// The logic mirrors ArgoCD's ItemExponentialRateLimiterWithAutoReset:
// if enough time has passed since the last request (≥ CoolDown), the
// failure counter resets automatically.
func (rl *RateLimiter) perIPDelay(ip string) time.Duration {
	rl.mu.Lock()
	defer rl.mu.Unlock()

	now := time.Now()
	st, ok := rl.perIP[ip]
	if !ok {
		rl.perIP[ip] = &ipState{failures: 1, lastSeen: now}
		return 0
	}

	// Auto-reset after cool-down (same concept as ArgoCD's coolDown check).
	if now.Sub(st.lastSeen) >= rl.cfg.CoolDown {
		st.failures = 1
		st.lastSeen = now
		st.blockedUtil = time.Time{}
		return 0
	}

	// Still within a block window?
	if now.Before(st.blockedUtil) {
		return st.blockedUtil.Sub(now)
	}

	// Record another hit.
	st.failures++
	st.lastSeen = now

	// Compute exponential delay: baseDelay × backoffFactor^(failures-1)
	backoff := float64(rl.cfg.BaseDelay.Nanoseconds()) * math.Pow(rl.cfg.BackoffFactor, float64(st.failures-1))
	if backoff > math.MaxInt64 {
		backoff = float64(rl.cfg.MaxDelay.Nanoseconds())
	}
	delay := time.Duration(backoff)
	if delay > rl.cfg.MaxDelay {
		delay = rl.cfg.MaxDelay
	}

	// Only enforce the delay once the per-IP rate exceeds the base.
	if delay > rl.cfg.BaseDelay {
		st.blockedUtil = now.Add(delay)
		return delay
	}
	return 0
}

// cleanup periodically reaps IP entries that haven't been seen within
// CoolDown, preventing unbounded memory growth.
func (rl *RateLimiter) cleanup() {
	ticker := time.NewTicker(rl.cfg.CleanupInterval)
	defer ticker.Stop()

	for {
		select {
		case <-rl.closeCh:
			return
		case <-ticker.C:
			rl.mu.Lock()
			cutoff := time.Now().Add(-rl.cfg.CoolDown)
			for ip, st := range rl.perIP {
				if st.lastSeen.Before(cutoff) {
					delete(rl.perIP, ip)
				}
			}
			rl.mu.Unlock()
		}
	}
}

// extractIP strips the port from RemoteAddr so different ephemeral ports
// from the same host are tracked together.
func extractIP(r *http.Request) string {
	// Try X-Forwarded-For first (common behind load balancers).
	// Take only the first entry — it's the original client IP.
	if xff := r.Header.Get("X-Forwarded-For"); xff != "" {
		ip := strings.TrimSpace(splitFirst(xff, ','))
		if ip != "" {
			return ip
		}
	}

	host, _, err := net.SplitHostPort(r.RemoteAddr)
	if err != nil {
		return r.RemoteAddr
	}
	return host
}

func splitFirst(s string, sep byte) string {
	for i := 0; i < len(s); i++ {
		if s[i] == sep {
			return s[:i]
		}
	}
	return s
}
