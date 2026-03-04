// Bhai, jab aap 'npm install hypertune' kar loge, toh yahan apna asli client import kar lena.
// Abhi ke liye yeh ek dummy hook hai taaki UI bina error ke ban jaye.
export function useFeatureFlags() {
  return {
    enablePromoBanner: true,    // Header me promo dikhane ke liye
    enableNewFooter: true,      // Footer ka naya design
    enableCryptoFeature: false, // Drawer me crypto ka option (abhi band hai)
  };
}
