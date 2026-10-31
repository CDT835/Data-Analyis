import os

# Bộ kiểm thử gửi rất nhiều yêu cầu trong vài giây; nới giới hạn tần suất mặc định (test_rotation_limits tự đặt lại giá trị nhỏ).
os.environ.setdefault("AIAR_RATE_PER_MIN", "1000000")
os.environ.setdefault("AIAR_AUTH_FAIL_PER_MIN", "1000000")
