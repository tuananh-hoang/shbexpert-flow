resource "aws_key_pair" "deploy" {
  key_name   = "${var.project}-deploy"
  public_key = var.ssh_public_key
}

resource "aws_instance" "app" {
  ami                    = var.ami
  instance_type          = var.instance_type
  subnet_id              = aws_subnet.lz.id
  vpc_security_group_ids = [aws_security_group.app.id]
  key_name               = aws_key_pair.deploy.key_name
  iam_instance_profile   = aws_iam_instance_profile.ssm.name
  user_data              = file("${path.module}/user_data.sh")

  root_block_device {
    volume_type = "gp3"
    volume_size = var.root_volume_gb
  }

  tags = { Name = "${var.project}-vm" }
}

# Elastic IP must live in the Local Zone's network border group — a normal
# region EIP (border group ap-southeast-1) cannot attach to a LZ instance.
resource "aws_eip" "app" {
  domain               = "vpc"
  network_border_group = var.az_group
  tags                 = { Name = "${var.project}-eip" }
}

resource "aws_eip_association" "app" {
  instance_id   = aws_instance.app.id
  allocation_id = aws_eip.app.id
}
