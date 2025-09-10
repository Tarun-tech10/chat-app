import React, { useState, useEffect, useRef } from 'react';
import axios from 'axios';

// Configure API URL
const API_URL = process.env.REACT_APP_API_URL || 'http://localhost:8000';
const WS_URL = API_URL.replace(/^https?:\/\//, '').replace(/\/$/, '');

// Set axios base URL for production
if (process.env.REACT_APP_API_URL) {
  axios.defaults.baseURL = API_URL;
}

function App() {
  const [username, setUsername] = useState('');
  const [isJoined, setIsJoined] = useState(false);
  const [messages, setMessages] = useState([]);
  const [inputMessage, setInputMessage] = useState('');
  const [socket, setSocket] = useState(null);
  const [isConnected, setIsConnected] = useState(false);
  const messagesEndRef = useRef(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  const joinChat = async () => {
    if (username.trim()) {
      try {
        // Try to get user first
        await axios.get(`/users/${username.trim()}`);
        setIsJoined(true);
        connectWebSocket();
      } catch (error) {
        // If not found, create user
        if (error.response && error.response.status === 404) {
          await axios.post('/users', null, { params: { username: username.trim() } });
          setIsJoined(true);
          connectWebSocket();
        } else {
          console.error('Error joining chat:', error);
        }
      }
    }
  };

  const connectWebSocket = () => {
    const wsProtocol = API_URL.startsWith('https') ? 'wss' : 'ws';
    const ws = new WebSocket(`${wsProtocol}://${WS_URL}/ws/${username}`);
    
    ws.onopen = () => {
      console.log('Connected to chat');
      setIsConnected(true);
    };

    ws.onmessage = (event) => {
      const data = JSON.parse(event.data);
      
      switch (data.type) {
        case 'history':
          setMessages(data.messages);
          break;
        case 'new_message':
          setMessages(prev => [...prev, data.message]);
          break;
        case 'user_joined':
          console.log(`${data.username} joined the chat`);
          break;
        case 'user_left':
          console.log(`${data.username} left the chat`);
          break;
        default:
          break;
      }
    };

    ws.onclose = () => {
      console.log('Disconnected from chat');
      setIsConnected(false);
    };

    ws.onerror = (error) => {
      console.error('WebSocket error:', error);
    };

    setSocket(ws);
  };

  const sendMessage = () => {
    if (inputMessage.trim() && socket && isConnected) {
      socket.send(JSON.stringify({
        type: 'message',
        content: inputMessage.trim()
      }));
      setInputMessage('');
    }
  };

  const handleKeyPress = (e) => {
    if (e.key === 'Enter') {
      sendMessage();
    }
  };

  if (!isJoined) {
    return (
      <div className="center-container">
        <h2>Enter your name</h2>
        <form
          onSubmit={e => {
            e.preventDefault();
            joinChat();
          }}
          style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '16px' }}
        >
          <input
            type="text"
            value={username}
            onChange={e => setUsername(e.target.value)}
            className="username-input"
            placeholder="Your name"
          />
          <button
            type="submit"
            className="join-chat-btn"
          >
            Join Chat
          </button>
        </form>
      </div>
    );
  }

  return (
    <div className="chat-container">
      <div className="chat-header">
        <h2>Real-time Chat</h2>
        <div>
          <span>Connected as: <strong>{username}</strong></span>
          {!isConnected && <span> (Reconnecting...)</span>}
        </div>
      </div>
      
      <div className="chat-messages">
        {messages.map((message, index) => (
          <div
            key={message.id || index}
            className={`message ${message.username === username ? 'own' : 'other'}`}
          >
            <div className="message-header">
              <strong>{message.username}</strong> • {new Date(message.timestamp).toLocaleTimeString()}
            </div>
            <div className="message-content">{message.content}</div>
          </div>
        ))}
        <div ref={messagesEndRef} />
      </div>

      <div className="chat-input-container">
        <input
          type="text"
          placeholder="Type a message..."
          value={inputMessage}
          onChange={(e) => setInputMessage(e.target.value)}
          onKeyPress={handleKeyPress}
          className="chat-input"
          disabled={!isConnected}
        />
        <button
          onClick={sendMessage}
          className="send-button"
          disabled={!isConnected || !inputMessage.trim()}
        >
          Send
        </button>
      </div>
    </div>
  );
}

export default App;