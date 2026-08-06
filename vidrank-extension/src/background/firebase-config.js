// src/js/firebase-config.js
// Firebase Auth only - no Firestore needed (we use backend API)
import { initializeApp } from "firebase/app";
import { getAuth } from "firebase/auth/web-extension";

const firebaseConfig = {
  apiKey: "AIzaSyAlRH6242b-yDFn5E9yfyIwof6LsL7nWp8",
  authDomain: "vidrank-5e540.firebaseapp.com",
  projectId: "vidrank-5e540",
  storageBucket: "vidrank-5e540.firebasestorage.app",
  messagingSenderId: "5551217356",
  appId: "1:5551217356:web:528d9a9443cfb0a0e58069",
  measurementId: "G-LTP9PYKR6F"
};

const app = initializeApp(firebaseConfig);
export const auth = getAuth(app);

console.log("[VidRank] Firebase Auth initialized (extension mode).");
