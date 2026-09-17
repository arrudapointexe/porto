import React, { useState, useEffect } from 'react'
import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom'
import Login from './pages/Login'
import Dashboard from './pages/Dashboard'
import History from './pages/History'
import './index.css'

function App() {
  const [user, setUser] = useState(null)

  useEffect(() => {
    const storedUser = localStorage.getItem('user_auth')
    if (storedUser) {
      setUser(JSON.parse(storedUser))
    }
  }, [])

  const handleLogin = (userData) => {
    localStorage.setItem('user_auth', JSON.stringify(userData))
    setUser(userData)
  }

  const handleLogout = () => {
    localStorage.removeItem('user_auth')
    setUser(null)
  }

  return (
    <Router>
      <Routes>
        <Route path="/login" element={!user ? <Login onLogin={handleLogin} /> : <Navigate to="/" />} />
        <Route path="/" element={user ? <Dashboard user={user} onLogout={handleLogout} /> : <Navigate to="/login" />} />
        <Route path="/history" element={user ? <History user={user} onLogout={handleLogout} /> : <Navigate to="/login" />} />
      </Routes>
    </Router>
  )
}

export default App
