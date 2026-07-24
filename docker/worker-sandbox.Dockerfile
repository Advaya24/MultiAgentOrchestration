FROM golang:1.25-alpine AS ddg_builder

ARG DDG_SEARCH_COMMIT=e532dec7e208dc7dbb05eb9b664c689ab194d7fe

RUN go install github.com/Djarvur/ddg-search/cmd/ddg-search@${DDG_SEARCH_COMMIT} \
    && go install github.com/Djarvur/ddg-search/cmd/page-dump@${DDG_SEARCH_COMMIT}

FROM python:3.13-alpine

COPY --from=ddg_builder /go/bin/ddg-search /go/bin/page-dump /usr/local/bin/

RUN addgroup -S worker \
    && adduser -S -G worker -h /workspace worker \
    && mkdir -p /workspace \
    && chown worker:worker /workspace

WORKDIR /workspace
USER worker

CMD ["sleep", "infinity"]
