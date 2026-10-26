package main

import (
	"context"
	"fmt"
	"github.com/mzydmer/deermate/backend/internal/controlplane"
	"log/slog"
	"net/http"
	"os"
	"os/signal"
	"strings"
	"syscall"
	"time"
)

func env(key, fallback string) string {
	if value := os.Getenv(key); value != "" {
		return value
	}
	return fallback
}
func main() {
	if len(os.Args) > 1 && os.Args[1] == "healthcheck" {
		client := &http.Client{Timeout: 4 * time.Second}
		resp, err := client.Get("http://127.0.0.1:8080/health/ready")
		if err != nil {
			os.Exit(1)
		}
		resp.Body.Close()
		if resp.StatusCode != 200 {
			os.Exit(1)
		}
		return
	}
	if err := run(); err != nil {
		slog.Error("control plane stopped", "error", err)
		os.Exit(1)
	}
}
func run() error {
	runtimeURL := env("DEERMATE_RUNTIME_URL", "http://127.0.0.1:8001")
	// Runtime owns its initial SQLAlchemy schema; wait until its migration has completed.
	client := &http.Client{Timeout: 2 * time.Second}
	deadline := time.Now().Add(120 * time.Second)
	for {
		r, e := client.Get(runtimeURL + "/health/ready")
		if e == nil {
			r.Body.Close()
			if r.StatusCode == 200 {
				break
			}
		}
		if time.Now().After(deadline) {
			return fmt.Errorf("runtime did not become ready before control-plane startup")
		}
		time.Sleep(time.Second)
	}
	store, err := controlplane.OpenStore(env("DEERMATE_DATABASE_PATH", "./data/deerflow.db"))
	if err != nil {
		return err
	}
	defer store.DB.Close()
	handler, err := controlplane.NewServer(store, controlplane.Config{RuntimeURL: runtimeURL, Origin: env("DEERMATE_ORIGIN", "http://localhost:2026"), AllowedHosts: strings.Split(env("DEERMATE_ALLOWED_HOSTS", "localhost:2026,127.0.0.1:2026,127.0.0.1:8080,control:8080"), ","), JWTSecret: os.Getenv("AUTH_JWT_SECRET")})
	if err != nil {
		return err
	}
	server := &http.Server{Addr: env("DEERMATE_LISTEN", ":8080"), Handler: handler, ReadHeaderTimeout: 5 * time.Second, ReadTimeout: 30 * time.Second, IdleTimeout: 60 * time.Second, MaxHeaderBytes: 32 << 10}
	ctx, stop := signal.NotifyContext(context.Background(), syscall.SIGTERM, syscall.SIGINT)
	defer stop()
	done := make(chan struct{})
	go func() {
		defer close(done)
		<-ctx.Done()
		shutdown, cancel := context.WithTimeout(context.Background(), 15*time.Second)
		defer cancel()
		_ = server.Shutdown(shutdown)
	}()
	slog.Info("Go control plane ready", "listen", server.Addr)
	err = server.ListenAndServe()
	stop()
	<-done
	if err == http.ErrServerClosed {
		return nil
	}
	return err
}
