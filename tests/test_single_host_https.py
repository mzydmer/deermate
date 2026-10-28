"""The optional public edge must preserve private application/desktop boundaries."""

import pytest
import yaml

from scripts import single_host, single_host_https


def bundle(tmp_path):
    source = single_host.compose("public-test", 2027)
    (tmp_path / "compose.yaml").write_text(yaml.safe_dump(source))
    return tmp_path


def test_public_ip_edge_keeps_private_services_and_exact_origin(tmp_path):
    target = bundle(tmp_path)
    before = (target / "compose.yaml").read_text()
    single_host_https.configure(target, "8.8.8.8")
    config = yaml.safe_load((target / "compose.yaml").read_text())
    services = config["services"]
    assert services["nginx"]["ports"] == ["127.0.0.1:2027:2026"]
    assert not services["gateway"].get("ports")
    assert not services["control"].get("ports")
    env = services["control"]["environment"]
    assert env["DEERMATE_ORIGIN"] == "https://8.8.8.8"
    assert "*" not in env["DEERMATE_ALLOWED_HOSTS"]
    assert set(env["DEERMATE_ALLOWED_HOSTS"].split(",")) >= {"8.8.8.8", "8.8.8.8:443"}
    edge = services["edge"]
    assert edge["image"] == single_host_https.CADDY_IMAGE
    assert edge["network_mode"] == "host"
    assert edge["cap_drop"] == ["ALL"]
    assert edge["cap_add"] == ["NET_BIND_SERVICE"]
    assert edge["read_only"]
    assert edge["mem_limit"] == edge["memswap_limit"] == "128m"
    assert not edge.get("env_file")
    assert "docker.sock" not in str(edge)
    assert all("home:" not in mount for mount in edge["volumes"])
    caddy = (target / "edge/Caddyfile").read_text()
    assert "https://8.8.8.8, :443" in caddy
    assert "@unknown_host not host 8.8.8.8" in caddy
    assert "respond @unknown_host 421" in caddy
    assert "profile shortlived" in caddy
    assert "admin 127.0.0.1:2019" in caddy
    assert "default_sni 8.8.8.8" in caddy
    assert "protocols h1 h2\n" in caddy
    assert "reverse_proxy 127.0.0.1:2027" in caddy
    assert "flush_interval -1" in caddy
    assert "tls internal" not in caddy
    assert (target / "compose.before-https.yaml").read_text() == before
    with pytest.raises(ValueError, match="already configured"):
        single_host_https.configure(target, "8.8.4.4")


@pytest.mark.parametrize("address", ["127.0.0.1", "10.0.0.1", "198.51.100.2", "0.0.0.0", "::1"])
def test_nonpublic_addresses_do_not_mutate_bundle(tmp_path, address):
    target = bundle(tmp_path)
    before = (target / "compose.yaml").read_text()
    with pytest.raises(ValueError):
        single_host_https.configure(target, address)
    assert (target / "compose.yaml").read_text() == before
    assert not (target / "edge").exists()


def test_unexpected_private_listener_is_not_silently_reconfigured(tmp_path):
    target = bundle(tmp_path)
    cfg = yaml.safe_load((target / "compose.yaml").read_text())
    cfg["services"]["nginx"]["ports"] = ["0.0.0.0:2027:2026"]
    (target / "compose.yaml").write_text(yaml.safe_dump(cfg))
    with pytest.raises(ValueError, match="private single-host"):
        single_host_https.configure(target, "8.8.8.8")
