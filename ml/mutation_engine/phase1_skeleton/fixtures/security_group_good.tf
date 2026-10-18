# Known-good security group config used by the ARGUS mutation engine (Phase 1 skeleton).

resource "aws_security_group" "app" {
  name        = "argus-example-app-sg"
  description = "Example security group with restricted ingress"

  ingress {
    description = "HTTPS from internal network only"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["10.0.0.0/16"] # ingress restricted to internal network
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}
