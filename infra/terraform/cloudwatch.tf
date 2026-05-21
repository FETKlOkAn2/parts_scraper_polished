resource "aws_sns_topic" "alerts" {
  name = "${local.prefix}-parts-pipeline-alerts"
}

resource "aws_sns_topic_subscription" "alerts_email" {
  count     = var.alerts_email == "" ? 0 : 1
  topic_arn = aws_sns_topic.alerts.arn
  protocol  = "email"
  endpoint  = var.alerts_email
}

# ---------- DLQ depth alarms ----------
resource "aws_cloudwatch_metric_alarm" "scraper_dlq" {
  alarm_name          = "${local.prefix}-scraper-dlq-not-empty"
  alarm_description   = "Scraper DLQ has messages; investigate failed shards."
  comparison_operator = "GreaterThanOrEqualToThreshold"
  evaluation_periods  = 1
  threshold           = 1
  metric_name         = "ApproximateNumberOfMessagesVisible"
  namespace           = "AWS/SQS"
  period              = 60
  statistic           = "Maximum"
  treat_missing_data  = "notBreaching"
  dimensions          = { QueueName = aws_sqs_queue.scraper_dlq.name }
  alarm_actions       = [aws_sns_topic.alerts.arn]
  ok_actions          = [aws_sns_topic.alerts.arn]
}

resource "aws_cloudwatch_metric_alarm" "proc_dlq" {
  alarm_name          = "${local.prefix}-image-proc-dlq-not-empty"
  alarm_description   = "Image-processing DLQ has messages; investigate failed shards."
  comparison_operator = "GreaterThanOrEqualToThreshold"
  evaluation_periods  = 1
  threshold           = 1
  metric_name         = "ApproximateNumberOfMessagesVisible"
  namespace           = "AWS/SQS"
  period              = 60
  statistic           = "Maximum"
  treat_missing_data  = "notBreaching"
  dimensions          = { QueueName = aws_sqs_queue.proc_dlq.name }
  alarm_actions       = [aws_sns_topic.alerts.arn]
  ok_actions          = [aws_sns_topic.alerts.arn]
}

# ---------- Queue stuck (no consumers) alarm ----------
resource "aws_cloudwatch_metric_alarm" "scraper_queue_stuck" {
  alarm_name          = "${local.prefix}-scraper-queue-stuck"
  alarm_description   = "Messages have been visible in the scraper queue for more than 30 minutes; workers may not be draining it."
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 3
  threshold           = 1800
  metric_name         = "ApproximateAgeOfOldestMessage"
  namespace           = "AWS/SQS"
  period              = 300
  statistic           = "Maximum"
  treat_missing_data  = "notBreaching"
  dimensions          = { QueueName = aws_sqs_queue.scraper.name }
  alarm_actions       = [aws_sns_topic.alerts.arn]
}

resource "aws_cloudwatch_metric_alarm" "proc_queue_stuck" {
  alarm_name          = "${local.prefix}-image-proc-queue-stuck"
  alarm_description   = "Messages have been visible in the image-proc queue for more than 30 minutes; workers may not be draining it."
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 3
  threshold           = 1800
  metric_name         = "ApproximateAgeOfOldestMessage"
  namespace           = "AWS/SQS"
  period              = 300
  statistic           = "Maximum"
  treat_missing_data  = "notBreaching"
  dimensions          = { QueueName = aws_sqs_queue.proc.name }
  alarm_actions       = [aws_sns_topic.alerts.arn]
}

# ---------- Dashboard ----------
resource "aws_cloudwatch_dashboard" "pipeline" {
  dashboard_name = "${local.prefix}-parts-pipeline"

  dashboard_body = jsonencode({
    widgets = [
      {
        type   = "metric"
        x      = 0
        y      = 0
        width  = 12
        height = 6
        properties = {
          title  = "SQS queue depth (visible messages)"
          region = var.region
          view   = "timeSeries"
          metrics = [
            ["AWS/SQS", "ApproximateNumberOfMessagesVisible", "QueueName", aws_sqs_queue.scraper.name],
            ["AWS/SQS", "ApproximateNumberOfMessagesVisible", "QueueName", aws_sqs_queue.proc.name],
            ["AWS/SQS", "ApproximateNumberOfMessagesVisible", "QueueName", aws_sqs_queue.scraper_dlq.name],
            ["AWS/SQS", "ApproximateNumberOfMessagesVisible", "QueueName", aws_sqs_queue.proc_dlq.name],
          ]
        }
      },
      {
        type   = "metric"
        x      = 12
        y      = 0
        width  = 12
        height = 6
        properties = {
          title  = "Worker fleet size"
          region = var.region
          view   = "timeSeries"
          metrics = [
            ["AWS/AutoScaling", "GroupInServiceInstances", "AutoScalingGroupName", aws_autoscaling_group.scraper.name],
            ["AWS/AutoScaling", "GroupInServiceInstances", "AutoScalingGroupName", aws_autoscaling_group.image_proc.name],
          ]
        }
      },
      {
        type   = "metric"
        x      = 0
        y      = 6
        width  = 12
        height = 6
        properties = {
          title  = "Message age in main queues"
          region = var.region
          view   = "timeSeries"
          metrics = [
            ["AWS/SQS", "ApproximateAgeOfOldestMessage", "QueueName", aws_sqs_queue.scraper.name],
            ["AWS/SQS", "ApproximateAgeOfOldestMessage", "QueueName", aws_sqs_queue.proc.name],
          ]
        }
      },
    ]
  })
}
