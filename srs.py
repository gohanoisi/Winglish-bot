import datetime

def update_srs(easiness, interval_days, consecutive_correct, q):
    e = float(easiness)
    i = float(interval_days)
    c = int(consecutive_correct or 0)
    q = int(q)

    # SM-2 由来の更新
    e = e + (0.1 - (5 - q) * (0.08 + (5 - q) * 0.02))
    if e < 1.3:
        e = 1.3

    if q < 3:
        c = 0
        i = 1
    else:
        c += 1
        i = 1 if c == 1 else round(i * e)

    next_review = datetime.date.today() + datetime.timedelta(days=int(i))
    return float(e), float(i), int(c), next_review