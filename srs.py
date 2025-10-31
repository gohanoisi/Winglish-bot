from datetime import date, timedelta

def update_srs(easiness, interval_days, consecutive_correct, quality: int):
    # quality: 5(覚えた/正解) / 2(忘れそう/不正解より)
    q = max(0, min(5, quality))
    if q >= 3:
        if consecutive_correct == 0:
            interval_days = 1
        elif consecutive_correct == 1:
            interval_days = 6
        else:
            interval_days = int(round(interval_days * easiness))
        consecutive_correct += 1
    else:
        consecutive_correct = 0
        interval_days = 1

    # easiness更新
    easiness = easiness + (0.1 - (5 - q) * (0.08 + (5 - q) * 0.02))
    easiness = max(1.3, round(easiness, 2))
    next_review = date.today() + timedelta(days=interval_days)
    return easiness, interval_days, consecutive_correct, next_review
