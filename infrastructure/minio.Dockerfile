# DocuSense AI — local MinIO server image.
#
# The community MinIO repository is archived; this setup follows the approved
# local MinIO architecture by building the pinned final security release from
# source instead of trusting a moving image tag:
# https://github.com/minio/minio/releases/tag/RELEASE.2025-10-15T17-29-55Z
#
# The first build downloads the Go toolchain image, the repository and all Go
# modules; it takes substantially longer than later cached starts.

ARG GO_BUILDER=golang:1.25-alpine
ARG RUNTIME=alpine:3.20

FROM ${GO_BUILDER} AS build
ARG MINIO_RELEASE=RELEASE.2025-10-15T17-29-55Z
RUN apk add --no-cache git
RUN git clone --depth 1 --branch "${MINIO_RELEASE}" https://github.com/minio/minio.git /src/minio
WORKDIR /src/minio
RUN CGO_ENABLED=0 go build -trimpath -ldflags "-s -w" -o /out/minio ./cmd

FROM ${RUNTIME}
# curl provides the container-internal TLS healthcheck used by docker-compose.yml.
RUN apk add --no-cache curl ca-certificates
COPY --from=build /out/minio /usr/bin/minio
EXPOSE 9000 9001
ENTRYPOINT ["/usr/bin/minio"]
CMD ["server", "--address", ":9000", "/data"]
