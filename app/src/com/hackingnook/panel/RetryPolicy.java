package com.hackingnook.panel;

/** Sleep between attempts: two short retries, then bounded outage backoff. */
public final class RetryPolicy {
    private RetryPolicy() { }
    public static int delaySeconds(int consecutiveFailures, int normalSeconds) {
        if (consecutiveFailures <= 0) return normalSeconds;
        if (consecutiveFailures <= 2) return 60;
        if (consecutiveFailures == 3) return 1800;
        return 3600;
    }
}
