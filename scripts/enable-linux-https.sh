#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cert_dir="$repo_root/.certs"
env_file="$repo_root/.env"
host_ip=""
days=365
start_stack=false
detect_requested=false
declare -a extra_dns=()
declare -a docker_command=()

usage() {
  cat <<'EOF'
Usage: ./scripts/enable-linux-https.sh [options]

Options:
  --ip ADDRESS      Override PUBLIC_IP and save it to .env
  --detect          Detect an address once and save it as PUBLIC_IP in .env
  --dns NAME        Additional DNS SAN; may be supplied more than once
  --days NUMBER     Certificate lifetime in days (default: 365)
  --start           Build and start the HTTP/HTTPS Docker Compose stack
  --help            Show this help
EOF
}

fail() {
  printf 'error: %s\n' "$*" >&2
  exit 1
}

valid_ipv4() {
  local candidate=$1 octet
  local -a parts
  IFS=. read -r -a parts <<<"$candidate"
  [[ ${#parts[@]} -eq 4 ]] || return 1
  for octet in "${parts[@]}"; do
    [[ $octet =~ ^[0-9]{1,3}$ ]] || return 1
    ((10#$octet <= 255)) || return 1
  done
}

detect_ip() {
  local detected=""
  if command -v ip >/dev/null 2>&1; then
    detected="$(ip -4 route get 1.1.1.1 2>/dev/null | awk '{for (i=1; i<=NF; i++) if ($i == "src") {print $(i+1); exit}}')"
  fi
  if [[ -z $detected ]]; then
    detected="$(hostname -I 2>/dev/null | awk '{for (i=1; i<=NF; i++) if ($i !~ /^127\./) {print $i; exit}}')"
  fi
  printf '%s' "$detected"
}

resolve_docker() {
  if command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then
    docker_command=(docker)
  elif command -v sudo >/dev/null 2>&1 && sudo -n docker info >/dev/null 2>&1; then
    docker_command=(sudo docker)
  else
    return 1
  fi
}

upsert_env() {
  local key=$1 value=$2 temporary
  temporary="$(mktemp "${env_file}.tmp.XXXXXX")"
  awk -v key="$key" -v value="$value" '
    BEGIN { found = 0 }
    $0 ~ "^" key "=" { print key "=" value; found = 1; next }
    { print }
    END { if (!found) print key "=" value }
  ' "$env_file" >"$temporary"
  mv "$temporary" "$env_file"
}

while (($#)); do
  case "$1" in
    --ip)
      (($# >= 2)) || fail '--ip requires an address'
      host_ip=$2
      shift 2
      ;;
    --dns)
      (($# >= 2)) || fail '--dns requires a name'
      extra_dns+=("$2")
      shift 2
      ;;
    --detect)
      detect_requested=true
      shift
      ;;
    --days)
      (($# >= 2)) || fail '--days requires a number'
      days=$2
      shift 2
      ;;
    --start)
      start_stack=true
      shift
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    *) fail "unknown option: $1" ;;
  esac
done

[[ $days =~ ^[0-9]+$ ]] && ((days > 0)) || fail '--days must be a positive integer'
[[ -f $env_file ]] || fail 'create and configure .env from .env.example first'

read_env() {
  local key=$1
  awk -F= -v key="$key" '$1 == key {sub(/^[^=]*=/, ""); gsub(/\r$/, ""); print; exit}' "$env_file"
}

if [[ -n $host_ip ]]; then
  upsert_env PUBLIC_IP "$host_ip"
elif $detect_requested; then
  host_ip="$(detect_ip)"
  valid_ipv4 "$host_ip" || fail 'could not auto-detect a valid IPv4 address; use --ip ADDRESS'
  upsert_env PUBLIC_IP "$host_ip"
else
  host_ip="$(read_env PUBLIC_IP)"
fi
valid_ipv4 "$host_ip" || fail 'set PUBLIC_IP in .env, or run once with --detect/--ip ADDRESS'

configured_dns="$(read_env PUBLIC_DNS_NAMES)"
declare -a dns_names=()
IFS=',' read -r -a env_dns <<<"$configured_dns"
for name in "${env_dns[@]}" "${extra_dns[@]}"; do
  [[ -n $name && ! $name =~ [[:space:],] ]] || continue
  if [[ ! " ${dns_names[*]} " =~ " ${name} " ]]; then
    dns_names+=("$name")
  fi
done

san="IP:${host_ip}"
for name in "${dns_names[@]}"; do
  san+=",DNS:${name}"
done

mkdir -p "$cert_dir"
generation_dir="$(mktemp -d "$cert_dir/.generate.XXXXXX")"
cleanup() {
  find "$generation_dir" -type f -delete 2>/dev/null || true
  rmdir "$generation_dir" 2>/dev/null || true
}
trap cleanup EXIT

openssl_args=(
  req -x509 -newkey rsa:2048
  -keyout "$generation_dir/tls.key"
  -out "$generation_dir/tls.crt"
  -sha256 -days "$days" -nodes
  -subj "/CN=${host_ip}"
  -addext "subjectAltName=${san}"
)

if command -v openssl >/dev/null 2>&1; then
  openssl "${openssl_args[@]}"
else
  resolve_docker || fail 'openssl is unavailable and Docker cannot be used'
  "${docker_command[@]}" run --rm --user "$(id -u):$(id -g)" \
    -v "$generation_dir:/certs" alpine/openssl \
    req -x509 -newkey rsa:2048 -keyout /certs/tls.key -out /certs/tls.crt \
    -sha256 -days "$days" -nodes -subj "/CN=${host_ip}" -addext "subjectAltName=${san}"
fi

chmod 600 "$generation_dir/tls.key"
chmod 644 "$generation_dir/tls.crt"
mv "$generation_dir/tls.key" "$cert_dir/tls.key"
mv "$generation_dir/tls.crt" "$cert_dir/tls.crt"

upsert_env HTTPS_BIND_ADDRESS 0.0.0.0
upsert_env TLS_CERT_FILE ./.certs/tls.crt
upsert_env TLS_KEY_FILE ./.certs/tls.key

printf '\nCertificate created for %s\n' "$host_ip"
if command -v openssl >/dev/null 2>&1; then
  openssl x509 -in "$cert_dir/tls.crt" -noout -subject -dates -ext subjectAltName
fi

https_port="$(awk -F= '$1 == "HTTPS_PORT" {print $2; exit}' "$env_file")"
https_port="${https_port:-8443}"
[[ $https_port =~ ^[0-9]+$ ]] && ((https_port >= 1 && https_port <= 65535)) \
  || fail 'HTTPS_PORT in .env must be between 1 and 65535'

if $start_stack; then
  ((${#docker_command[@]})) || resolve_docker || fail 'Docker daemon is unavailable'
  cd "$repo_root"
  "${docker_command[@]}" compose -f compose.yaml -f compose.https.yaml \
    --profile https up -d --build --wait
  # The certificate path stays constant, so force nginx to reload replaced files.
  "${docker_command[@]}" compose -f compose.yaml -f compose.https.yaml \
    --profile https up -d --force-recreate --wait web-https
  if command -v curl >/dev/null 2>&1; then
    curl --insecure --fail --silent --show-error \
      "https://127.0.0.1:${https_port}/api/health" >/dev/null
    printf 'HTTPS health check: OK\n'
  fi
fi

cat <<EOF

Windows URL: https://${host_ip}:${https_port}
Public certificate to copy to Windows: $cert_dir/tls.crt
Never copy the private key: $cert_dir/tls.key

After copying tls.crt to Windows, trust it for the current user with:
  .\\scripts\\Install-DevCertificate.ps1 -CertificatePath .\\tls.crt
EOF
