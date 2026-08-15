#!/usr/bin/env bash
set -euo pipefail

CERT_DIR="${1:-services/api-server/certs}"
mkdir -p "$CERT_DIR"
umask 077

openssl req \
  -x509 \
  -newkey rsa:2048 \
  -nodes \
  -keyout "$CERT_DIR/saml_sp.key" \
  -out "$CERT_DIR/saml_sp.crt" \
  -days 1 \
  -subj "/CN=Harness CI SAML SP" \
  >/dev/null 2>&1

echo "Generated ephemeral SAML SP test credentials in $CERT_DIR"
