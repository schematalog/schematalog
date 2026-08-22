# schematalog-s3

An S3 storage backend for [Schematalog](../../README.md), and the worked example of a
backend living outside the registry.

```shell
SCHEMATALOG_STORAGE_URL="s3://my-bucket/schemas?region=eu-west-2"
```

It implements the five required `SchemaRepository` methods and inherits the rest,
including the rule for which version counts as latest. Installing it is the whole of
registration: the `schematalog.storage` entry point in `pyproject.toml` tells Schematalog
which scheme it answers to.

## Options

| Parameter | Default | Description |
| --- | --- | --- |
| `region` | `us-east-1` | AWS region of the bucket. |
| `endpoint_url` | *(none)* | Override for S3-compatible stores (MinIO, Ceph). |

Credentials come from the ordinary AWS chain - environment, shared config, instance
role - and are deliberately not accepted in the URL, which tends to end up in logs and
process listings.
