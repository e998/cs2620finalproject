const socket = io({transports: ['websocket']});
const chatForm = document.getElementById('chat-form');
const chatInput = document.getElementById('chat-input');
const chatBox = document.getElementById('chat-box');

// Join a room based on product and buyer/seller IDs
const room = chatForm.dataset.room;
const receiverId = chatForm.dataset.receiverId;
const productId = chatForm.dataset.productId;
socket.emit('join', {room: room});

chatForm.addEventListener('submit', function(e) {
    e.preventDefault();
    const message = chatInput.value.trim();
    if (message) {
        socket.emit('chat_message', {
            room: room,
            message: message,
            receiver_id: receiverId,
            product_id: productId
        });
        chatInput.value = '';
    }
});

socket.on('chat_message', function(data) {
    const msgDiv = document.createElement('div');
    msgDiv.className = 'mb-2';
    msgDiv.innerHTML = `<strong>${data.username}:</strong> ${data.message} <span class="text-muted small">${data.timestamp || ''}</span>`;
    chatBox.appendChild(msgDiv);
    chatBox.scrollTop = chatBox.scrollHeight;
});
