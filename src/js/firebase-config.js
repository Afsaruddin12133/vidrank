// src/js/firebase-config.js
import { initializeApp } from "firebase/app";
import { getAuth } from "firebase/auth/web-extension";
import { getFirestore } from "firebase/firestore";

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
export const db = getFirestore(app);

console.log("[VidRank] Firebase Modular SDK successfully initialized.");
