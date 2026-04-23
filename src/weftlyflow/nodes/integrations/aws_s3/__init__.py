"""AWS S3 integration — bucket + object ops with SigV4 signing.

Exposes the top-level ``NODE`` attribute consumed by the built-in node
discovery in :mod:`weftlyflow.nodes.discovery`.
"""

from __future__ import annotations

from weftlyflow.nodes.integrations.aws_s3.node import AwsS3Node

NODE = AwsS3Node

__all__ = ["NODE", "AwsS3Node"]
