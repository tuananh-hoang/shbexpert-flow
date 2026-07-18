# --- Look up the account's default VPC + its internet gateway ------------
data "aws_vpc" "default" {
  default = true
}

data "aws_internet_gateway" "default" {
  filter {
    name   = "attachment.vpc-id"
    values = [data.aws_vpc.default.id]
  }
}

# --- Opt into the Hanoi Local Zone group ---------------------------------
# Local Zones are off by default; nothing can be created in the zone until
# its group is opted in. This calls ModifyAvailabilityZoneGroup.
resource "aws_ec2_availability_zone_group" "hanoi" {
  group_name    = var.az_group
  opt_in_status = "opted-in"
}

# Opt-in status flips quickly, but the zone can take a couple of minutes to
# become usable for subnet/instance creation — give it a buffer.
resource "time_sleep" "wait_optin" {
  depends_on      = [aws_ec2_availability_zone_group.hanoi]
  create_duration = "120s"
}

# --- Public subnet inside the Local Zone ---------------------------------
resource "aws_subnet" "lz" {
  vpc_id                  = data.aws_vpc.default.id
  cidr_block              = var.subnet_cidr
  availability_zone       = var.local_zone
  map_public_ip_on_launch = true

  tags = { Name = "${var.project}-lz-subnet" }

  depends_on = [time_sleep.wait_optin]
}

resource "aws_route_table" "public" {
  vpc_id = data.aws_vpc.default.id

  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = data.aws_internet_gateway.default.id
  }

  tags = { Name = "${var.project}-public-rt" }
}

resource "aws_route_table_association" "lz" {
  subnet_id      = aws_subnet.lz.id
  route_table_id = aws_route_table.public.id
}

# --- Security group: HTTP/HTTPS open, SSH locked to operator IP ----------
resource "aws_security_group" "app" {
  name        = "${var.project}-sg"
  description = "SHBExpert Flow single-VM: web (80/443) public, SSH restricted"
  vpc_id      = data.aws_vpc.default.id

  ingress {
    description = "HTTP (Caddy ACME + redirect)"
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  ingress {
    description = "HTTPS (app)"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  ingress {
    description = "SSH (operator only)"
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = [var.ssh_allow_cidr]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = { Name = "${var.project}-sg" }
}
