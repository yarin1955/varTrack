package middlewares

import (
	"errors"
	"log/slog"
	"sync"
	"time"
)

// CircuitState represents the state of a circuit breaker.
//
// Modeled after sony/gobreaker's three-state machine and informed by
// ArgoCD's failureRetryRoundTripper (util-kube/failureretrywrapper.go)
// which decides whether to retry based on error type and failure count.
type CircuitState int

const (
	CircuitClosed   CircuitState = iota // healthy — requests flow through
	CircuitOpen                         // tripped — requests fail fast
	CircuitHalfOpen                     // probing — limited requests to test recovery
)

func (s CircuitState) String() string {
	switch s {
	case CircuitClosed:
		return "closed"
	case CircuitOpen:
		return "open"
	case CircuitHalfOpen:
		return "half-open"
	default:
		return "unknown"
	}
}

// ErrCircuitOpen is returned when the circuit breaker is open and the
// request is rejected without calling the backend.
var ErrCircuitOpen = errors.New("circuit breaker is open")

// CircuitBreakerConfig configures the breaker thresholds.
//
// ArgoCD's shouldRetry() in failureRetryRoundTripper uses a simple
// counter + sleep pattern. We extend that into a proper state machine
// with timeout-based recovery, similar to sony/gobreaker.
type CircuitBreakerConfig struct {
	// MaxFailures is the number of consecutive failures before the
	// circuit transitions from Closed → Open.
	MaxFailures int

	// OpenTimeout is how long the circuit stays Open before moving
	// to HalfOpen for a probe request.
	OpenTimeout time.Duration

	// HalfOpenMaxSuccesses is the number of consecutive successes in
	// HalfOpen required to return to Closed.
	HalfOpenMaxSuccesses int
}

// DefaultCircuitBreakerConfig returns sensible defaults for a webhook
// gateway where the orchestrator timeout is 10s.
func DefaultCircuitBreakerConfig() CircuitBreakerConfig {
	return CircuitBreakerConfig{
		MaxFailures:          5,
		OpenTimeout:          30 * time.Second,
		HalfOpenMaxSuccesses: 2,
	}
}

// CircuitBreaker implements a thread-safe three-state circuit breaker.
//
// References:
//   - ArgoCD util-kube/failureretrywrapper.go: tracks failure count,
//     calls shouldRetry() checking IsInternalError/IsTimeout/IsTooManyRequests.
//   - ArgoCD util-grpc/errors.go: maps gRPC codes to retryable vs non-retryable.
//   - ArgoCD reposerver NewConnection(): timeout interceptor wraps every
//     call, similar to how our breaker wraps ProcessWebhook.
type CircuitBreaker struct {
	mu               sync.Mutex
	cfg              CircuitBreakerConfig
	state            CircuitState
	consecutiveFails int
	consecutiveSucc  int
	lastFailure      time.Time
	lastStateChange  time.Time
}

func NewCircuitBreaker(cfg CircuitBreakerConfig) *CircuitBreaker {
	return &CircuitBreaker{
		cfg:             cfg,
		state:           CircuitClosed,
		lastStateChange: time.Now(),
	}
}

// Allow checks whether a request should be permitted through the breaker.
// Returns true if the request may proceed, false if it should fail fast.
func (cb *CircuitBreaker) Allow() bool {
	cb.mu.Lock()
	defer cb.mu.Unlock()

	switch cb.state {
	case CircuitClosed:
		return true

	case CircuitOpen:
		// Check if OpenTimeout has elapsed → transition to HalfOpen.
		if time.Since(cb.lastStateChange) >= cb.cfg.OpenTimeout {
			cb.transitionTo(CircuitHalfOpen)
			return true // allow one probe request
		}
		return false

	case CircuitHalfOpen:
		// In HalfOpen, allow limited requests for probing.
		return true
	}
	return false
}

// RecordSuccess records a successful call.
func (cb *CircuitBreaker) RecordSuccess() {
	cb.mu.Lock()
	defer cb.mu.Unlock()

	switch cb.state {
	case CircuitHalfOpen:
		cb.consecutiveSucc++
		if cb.consecutiveSucc >= cb.cfg.HalfOpenMaxSuccesses {
			cb.transitionTo(CircuitClosed)
		}
	case CircuitClosed:
		cb.consecutiveFails = 0
	}
}

// RecordFailure records a failed call.
func (cb *CircuitBreaker) RecordFailure() {
	cb.mu.Lock()
	defer cb.mu.Unlock()

	cb.lastFailure = time.Now()

	switch cb.state {
	case CircuitClosed:
		cb.consecutiveFails++
		if cb.consecutiveFails >= cb.cfg.MaxFailures {
			cb.transitionTo(CircuitOpen)
		}
	case CircuitHalfOpen:
		// Any failure in HalfOpen trips back to Open.
		cb.transitionTo(CircuitOpen)
	}
}

// State returns the current state of the circuit breaker.
func (cb *CircuitBreaker) State() CircuitState {
	cb.mu.Lock()
	defer cb.mu.Unlock()
	return cb.state
}

// transitionTo changes the breaker state. Must be called with mu held.
func (cb *CircuitBreaker) transitionTo(newState CircuitState) {
	if cb.state == newState {
		return
	}
	prev := cb.state
	cb.state = newState
	cb.lastStateChange = time.Now()
	cb.consecutiveFails = 0
	cb.consecutiveSucc = 0

	slog.Warn("circuit breaker state change",
		"from", prev.String(),
		"to", newState.String(),
	)
}
