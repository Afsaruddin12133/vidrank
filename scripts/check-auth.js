/**
 * Simple Firebase Authentication Checker
 * 
 * Checks if user is logged in and saves the data.
 * Run this in browser console (F12).
 */

(function checkAuth() {
  console.log('🔍 Checking Firebase Authentication...\n');

  // Get Firebase data from localStorage
  const firebaseKey = 'firebase:authUser:AIzaSyAlRH6242b-yDFn5E9yfyIwof6LsL7nWp8:[DEFAULT]';
  const userDataStr = localStorage.getItem(firebaseKey);

  if (!userDataStr) {
    console.log('❌ User is NOT logged in');
    console.log('   No Firebase auth data found');
    return { isAuthenticated: false };
  }

  const userData = JSON.parse(userDataStr);

  // Check if authenticated
  const isAuthenticated = !!(userData.uid && userData.email);

  if (isAuthenticated) {
    console.log('✅ User IS authenticated!\n');
    console.log('👤 User Info:');
    console.log(`   UID:   ${userData.uid}`);
    console.log(`   Email: ${userData.email}`);
    console.log(`   Name:  ${userData.displayName}`);
    console.log(`   Email Verified: ${userData.emailVerified ? 'Yes' : 'No'}`);

    // Check token
    if (userData.stsTokenManager?.accessToken) {
      const token = userData.stsTokenManager.accessToken;
      const expiry = new Date(userData.stsTokenManager.expirationTime);
      const now = new Date();
      const isExpired = expiry < now;

      console.log('\n🔑 Token Info:');
      console.log(`   Status: ${isExpired ? '❌ Expired' : '✅ Valid'}`);
      console.log(`   Expires: ${expiry.toLocaleString()}`);

      if (!isExpired) {
        const minutesLeft = Math.floor((expiry - now) / 1000 / 60);
        console.log(`   Time Left: ${minutesLeft} minutes`);
      }

      // Decode token to get project ID
      const payload = decodeToken(token);
      if (payload?.aud) {
        console.log(`   Project ID: ${payload.aud}`);
        console.log('\n💡 Add to backend/.dev.vars:');
        console.log(`   AUTH_PROJECT_ID="${payload.aud}"`);
      }
    }

    // Return data
    return {
      isAuthenticated: true,
      uid: userData.uid,
      email: userData.email,
      name: userData.displayName,
      token: userData.stsTokenManager?.accessToken,
      projectId: decodeToken(userData.stsTokenManager?.accessToken)?.aud
    };

  } else {
    console.log('❌ User is NOT authenticated');
    return { isAuthenticated: false };
  }
})();

// Helper to decode JWT token
function decodeToken(token) {
  if (!token) return null;
  try {
    const payload = token.split('.')[1];
    const padding = '='.repeat((4 - payload.length % 4) % 4);
    const decoded = atob(payload.replace(/-/g, '+').replace(/_/g, '/') + padding);
    return JSON.parse(decoded);
  } catch (e) {
    return null;
  }
}
