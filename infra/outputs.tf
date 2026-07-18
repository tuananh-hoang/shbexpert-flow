output "public_ip" {
  description = "Elastic IP of the VM."
  value       = aws_eip.app.public_ip
}

output "instance_id" {
  value = aws_instance.app.id
}

output "app_domain" {
  description = "Live HTTPS host (sslip.io resolves the embedded IP — no DNS setup needed)."
  value       = "app.${replace(aws_eip.app.public_ip, ".", "-")}.sslip.io"
}

output "app_url" {
  value = "https://app.${replace(aws_eip.app.public_ip, ".", "-")}.sslip.io"
}

output "ssh_command" {
  description = "SSH in (private key lives in the scratchpad, not the repo)."
  value       = "ssh -i <path>/shbexpert.pem ubuntu@${aws_eip.app.public_ip}"
}
