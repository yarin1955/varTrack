package middlewares

import (
	"fmt"
	"log/slog"
	"math"
	"net"
	"net/http"
	"strconv"
	"strings"
	"sync"
	"time"

	"golang.org/x/time/rate"
)

// RateLimiterConfig controls both global and per-key limits.
//
// Mirrors ArgoCD's AppControllerRateLimiterConfig (pkg-ratelimiter/ratelimiter.go)
// which has BucketSize, BucketQPS, FailureCoolDown, BaseDelay, MaxDelay,
// BackoffFactor, and the session manager's envLoginMaxFailCount /
// envLoginFailureWindowSeconds for per-user failure tracking.
type RateLimiterConfig struct {
	// Global token-bucket — protects the service as a whole.
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
//
// Now also emits standardized rate limit headers on every response,
// following IETF draft-ietf-httpapi-ratelimit-headers:
//   - X-RateLimit-Limit:     maximum requests per window (bucket size)
//   - X-RateLimit-Remaining: tokens left in the global bucket
//   - X-RateLimit-Reset:     seconds until the bucket is fully replenished
//
// ArgoCD's session manager (sessionmanager.go) tracks a similar failure
// window with configurable max failures and window duration, reporting
// state back to the caller. We surface equivalent data via HTTP headers.
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
//
// Every response now includes X-RateLimit-* headers so callers can
// proactively throttle before hitting 429s. This is developer-friendly
// and follows the approach used by GitHub's API, which ArgoCD's webhook
// handler ultimately receives traffic from.
func (rl *RateLimiter) Middleware(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		// Always emit rate limit headers — even on success.
		// X-RateLimit-Limit: the bucket capacity.
		// X-RateLimit-Remaining: current tokens available (approximate).
		// X-RateLimit-Reset: seconds until bucket is fully replenished.
		rl.setRateLimitHeaders(w)

		// 1. Global bucket — fast path, no per-key state.
		if !rl.global.Allow() {
			slog.Warn("rate limit: global bucket exhausted")
			w.Header().Set("Retry-After", "1")
			writeRateLimitError(w, "Too Many Requests")
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
				writeRateLimitError(w, "Too Many Requests")
				return
			}
		}

		next.ServeHTTP(w, r)
	})
}

// setRateLimitHeaders populates the X-RateLimit-* headers on the response.
//
// These follow the IETF draft-ietf-httpapi-ratelimit-headers convention:
//   - X-RateLimit-Limit:     maximum burst capacity (BucketSize)
//   - X-RateLimit-Remaining: approximate tokens remaining
//   - X-RateLimit-Reset:     seconds until the bucket is fully replenished
//
// The "Remaining" value is approximate because golang.org/x/time/rate
// uses a continuous refill model rather than fixed windows. We compute
// the floor of available tokens at this instant.
func (rl *RateLimiter) setRateLimitHeaders(w http.ResponseWriter) {
	limit := rl.cfg.BucketSize
	remaining := int(rl.global.Tokens())
	if remaining < 0 {
		remaining = 0
	}

	// Reset: seconds until bucket reaches capacity.
	// deficit / refill-rate = seconds to full.
	deficit := limit - remaining
	var resetSeconds int
	if deficit > 0 && rl.cfg.BucketQPS > 0 {
		resetSeconds = int(math.Ceil(float64(deficit) / rl.cfg.BucketQPS))
	}

	w.Header().Set("X-RateLimit-Limit", strconv.Itoa(limit))
	w.Header().Set("X-RateLimit-Remaining", strconv.Itoa(remaining))
	w.Header().Set("X-RateLimit-Reset", strconv.Itoa(resetSeconds))
}

// writeRateLimitError writes a 429 response in JSON format for
// consistency with the rest of the API (improvement #5).
func writeRateLimitError(w http.ResponseWriter, message string) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(http.StatusTooManyRequests)
	fmt.Fprintf(w, `{"error":%q,"status":429}`, message)
}

// Close stops the background cleanup goroutine.
func (rl *RateLimiter) Close() {
	close(rl.closeCh)
}

// perIPDelay returns how long the caller must wait before the next
// request is allowed. Zero means the request may proceed immediately.
//
// Mirrors ArgoCD's ItemExponentialRateLimiterWithAutoReset
// (pkg-ratelimiter/ratelimiter.go): if enough time has passed since the
// last request (≥ CoolDown), the failure counter resets automatically.
func (rl *RateLimiter) perIPDelay(ip string) time.Duration {
	rl.mu.Lock()
	defer rl.mu.Unlock()

	now := time.Now()
	st, ok := rl.perIP[ip]
	if !ok {
		rl.perIP[ip] = &ipState{failures: 1, lastSeen: now}
		return 0
	}

	// Auto-reset after cool-down.
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

	st.failures++
	st.lastSeen = now

	// Compute exponential delay: baseDelay × backoffFactor^(failures-1)
	// Same formula as Flux's ItemExponentialRateLimiterWithAutoReset.When()
	backoff := float64(rl.cfg.BaseDelay.Nanoseconds()) * math.Pow(rl.cfg.BackoffFactor, float64(st.failures-1))
	if backoff > math.MaxInt64 {
		backoff = float64(rl.cfg.MaxDelay.Nanoseconds())
	}
	delay := time.Duration(backoff)
	if delay > rl.cfg.MaxDelay {
		delay = rl.cfg.MaxDelay
	}

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
		if parts := strings.SplitN(xff, ",", 2); len(parts) > 0 {
			ip := strings.TrimSpace(parts[0])
			if ip != "" {
				return ip
			}
		}
	}

	host, _, err := net.SplitHostPort(r.RemoteAddr)
	if err != nil {
		return r.RemoteAddr
	}
	return host
}
