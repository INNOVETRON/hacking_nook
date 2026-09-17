import com.hackingnook.panel.RetryPolicy;
public class RetryPolicyTest {
    public static void main(String[] args) {
        int[] expected = {7200,60,60,1800,3600,3600,3600};
        for (int i=0; i<expected.length; i++) {
            if (RetryPolicy.delaySeconds(i,7200)!=expected[i]) throw new AssertionError("retry " + i);
        }
        if (RetryPolicy.delaySeconds(0,900)!=900) throw new AssertionError("success resets delay");
        System.out.println("Retry policy passed: 1m, 1m, 30m, 1h; success restores server interval");
    }
}
