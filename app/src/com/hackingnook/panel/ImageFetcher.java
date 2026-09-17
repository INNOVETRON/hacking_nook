package com.hackingnook.panel;

import android.graphics.Bitmap;
import android.graphics.BitmapFactory;
import android.util.Log;

import java.io.BufferedInputStream;
import java.io.InputStream;
import java.net.HttpURLConnection;
import java.net.URL;

/**
 * Fetches one image over plain HTTP.
 *
 * Deliberately dumb: no HTTPS, no auth, no retries. Android 2.1 cannot do TLS
 * 1.2 or SNI, so this app is designed to talk to a server on your own LAN over
 * http://. If we ever need HTTPS we have to bundle SpongyCastle, the way the
 * TRMNL client does.
 */
public final class ImageFetcher {

    private static final String TAG = "NookPanel";
    private static final int CONNECT_TIMEOUT_MS = 15000;
    private static final int READ_TIMEOUT_MS = 30000;

    private ImageFetcher() {
    }

    /** @return the decoded bitmap, or null if anything at all went wrong. */
    public static Bitmap fetch(String urlString, android.content.Context context) {
        // Froyo and earlier have a broken HttpURLConnection keep-alive pool that
        // hands out already-closed sockets. Eclair is worse. Just disable it.
        System.setProperty("http.keepAlive", "false");

        HttpURLConnection connection = null;
        InputStream stream = null;
        try {
            URL url = new URL(urlString);
            connection = (HttpURLConnection) url.openConnection();
            connection.setConnectTimeout(CONNECT_TIMEOUT_MS);
            connection.setReadTimeout(READ_TIMEOUT_MS);
            connection.setRequestProperty("User-Agent", "NookPanel/0.4 (BNRV300)");
            connection.setRequestProperty("Connection", "close");

            android.content.Intent battery = context.registerReceiver(null,
                    new android.content.IntentFilter(android.content.Intent.ACTION_BATTERY_CHANGED));
            if (battery != null) {
                int level = battery.getIntExtra("level", -1);
                int scale = battery.getIntExtra("scale", -1);
                if (level >= 0 && scale > 0) {
                    connection.setRequestProperty("X-Nook-Battery", String.valueOf(Math.min(100L, level * 100L / scale)));
                    connection.setRequestProperty("X-Nook-Charging", battery.getIntExtra("plugged", 0) != 0 ? "1" : "0");
                }
            }
            connection.setRequestProperty("X-Nook-Failures", String.valueOf(Config.prefs(context).getInt("failed_fetches", 0)));
            int status = connection.getResponseCode();
            // Accept settings even on a 503 so recovery can use the new interval.
            int interval = connection.getHeaderFieldInt("X-Nook-Refresh-Seconds", -1);
            if (interval >= 60 && interval <= 86400) {
                Config.prefs(context).edit().putInt(Config.KEY_INTERVAL, interval).commit();
            }
            if (status != HttpURLConnection.HTTP_OK) {
                Log.w(TAG, "HTTP " + status + " from " + urlString);
                return null;
            }

            stream = new BufferedInputStream(connection.getInputStream(), 8192);

            // 256 MB of RAM total, so decode straight to the 8-bit-ish config
            // the e-ink panel can actually show rather than full ARGB_8888.
            BitmapFactory.Options options = new BitmapFactory.Options();
            options.inPreferredConfig = Bitmap.Config.RGB_565;
            options.inPurgeable = true;

            return BitmapFactory.decodeStream(stream, null, options);
        } catch (Throwable t) {
            // OutOfMemoryError is an Error, not an Exception, and is a very real
            // possibility here — catch it rather than dying.
            Log.w(TAG, "fetch failed: " + t);
            return null;
        } finally {
            if (stream != null) {
                try {
                    stream.close();
                } catch (Exception ignored) {
                }
            }
            if (connection != null) {
                connection.disconnect();
            }
        }
    }
}
