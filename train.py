import numpy as np
import cupy as cp
from tqdm import tqdm
import matplotlib.pyplot as plt
import os
from sklearn.metrics import mean_squared_error
from sklearn.preprocessing import StandardScaler
import pandas as pd
import logging
import matplotlib.animation as animation

logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s',
                    handlers=[
                        logging.FileHandler("log.txt", mode='w', encoding='utf-8'),
                        logging.StreamHandler()
                    ])

class ShallowNeuralNetwork:
    def __init__(self, input_size, hidden_size, output_size, learning_rate=0.01):
        self.input_size = input_size
        self.hidden_size = hidden_size
        self.output_size = output_size
        self.learning_rate = learning_rate
        self.beta1 = 0.9
        self.beta2 = 0.999
        self.epsilon = 1e-8
        self.t = 0
        
        self.W1, self.b1, self.W2, self.b2 = self.initialize_weights()
        self.initialize_adam_parameters()

    def initialize_weights(self):
        W1 = cp.random.randn(self.hidden_size, self.input_size) * 0.01
        b1 = cp.zeros((self.hidden_size, 1))
        W2 = cp.random.randn(self.output_size, self.hidden_size) * 0.01
        b2 = cp.zeros((self.output_size, 1))
        return W1, b1, W2, b2
    
    def initialize_adam_parameters(self):
        self.mW1, self.vW1 = cp.zeros_like(self.W1), cp.zeros_like(self.W1)
        self.mb1, self.vb1 = cp.zeros_like(self.b1), cp.zeros_like(self.b1)
        self.mW2, self.vW2 = cp.zeros_like(self.W2), cp.zeros_like(self.W2)
        self.mb2, self.vb2 = cp.zeros_like(self.b2), cp.zeros_like(self.b2)
    
    def forward(self, x):
        self.z1 = cp.dot(self.W1, x) + self.b1
        self.a1 = cp.tanh(self.z1)
        self.z2 = cp.dot(self.W2, self.a1) + self.b2
        self.output = self.z2 
        return self.output
    
    def predict(self, X):
        self.forward(X)
        return self.output

    def backward(self, x, y):
        m = x.shape[1]
        dz2 = self.output - y
        dW2 = (1/m) * cp.dot(dz2, self.a1.T)
        db2 = (1/m) * cp.sum(dz2, axis=1, keepdims=True)
        dz1 = cp.dot(self.W2.T, dz2) * (1 - cp.power(self.a1, 2))
        dW1 = (1/m) * cp.dot(dz1, x.T)
        db1 = (1/m) * cp.sum(dz1, axis=1, keepdims=True)
        self.update_weights(dW1, db1, dW2, db2)

    def update_weights(self, dW1, db1, dW2, db2):
        self.t += 1
        def adam_update(m, v, grad, beta1, beta2, epsilon, t):
            m = beta1 * m + (1 - beta1) * grad
            v = beta2 * v + (1 - beta2) * cp.power(grad, 2)
            m_hat = m / (1 - cp.power(beta1, t))
            v_hat = v / (1 - cp.power(beta2, t))
            return m, v, m_hat / (cp.sqrt(v_hat) + epsilon)
        
        self.mW1, self.vW1, mW1_hat = adam_update(self.mW1, self.vW1, dW1, self.beta1, self.beta2, self.epsilon, self.t)
        self.mb1, self.vb1, mb1_hat = adam_update(self.mb1, self.vb1, db1, self.beta1, self.beta2, self.epsilon, self.t)
        self.mW2, self.vW2, mW2_hat = adam_update(self.mW2, self.vW2, dW2, self.beta1, self.beta2, self.epsilon, self.t)
        self.mb2, self.vb2, mb2_hat = adam_update(self.mb2, self.vb2, db2, self.beta1, self.beta2, self.epsilon, self.t)

        self.W1 -= self.learning_rate * mW1_hat
        self.b1 -= self.learning_rate * mb1_hat
        self.W2 -= self.learning_rate * mW2_hat
        self.b2 -= self.learning_rate * mb2_hat
            
    def train(self, X, y, X_val, y_val, epochs=1, batch_size=1024, patience=10):
        losses, val_losses = [], []
        best_val_loss, best_weights = float('inf'), None
        epochs_no_improve, stopped_epoch = 0, 0
        num_batches = (X.shape[1] + batch_size - 1) // batch_size
        total_steps = epochs * num_batches
        parameters_history = []

        with tqdm(total=total_steps, desc="Training Progress") as bar:
            for epoch in range(epochs):
                for i in range(0, X.shape[1], batch_size):
                    x_batch = X[:, i:i + batch_size]
                    y_batch = y[:, i:i + batch_size]
                    self.forward(x_batch)
                    self.backward(x_batch, y_batch)
                    bar.update(1)

                y_pred_train = self.predict(X)
                loss = mean_squared_error(y.get(), y_pred_train.get())
                losses.append(loss)

                y_pred_val = self.predict(X_val)
                val_loss = mean_squared_error(y_val.get(), y_pred_val.get())
                val_losses.append(val_loss)

                # 儲存當前的參數
                parameters_history.append((self.W1.get(), self.b1.get(), self.W2.get(), self.b2.get()))

                if val_loss < best_val_loss:
                    best_val_loss, best_weights = val_loss, (self.W1.copy(), self.b1.copy(), self.W2.copy(), self.b2.copy())
                    epochs_no_improve = 0
                else:
                    epochs_no_improve += 1

                if epochs_no_improve >= patience:
                    stopped_epoch = epoch
                    break

            if best_weights is not None:
                self.W1, self.b1, self.W2, self.b2 = best_weights
            
            return losses, val_losses, stopped_epoch, parameters_history
        
    def __str__(self):
        return f'\nW1={self.W1}\nb1={self.b1}\nW2={self.W2}\nb2={self.b2}'
    
    def save(self, file_path):
        np.savez(file_path, 
                    W1=self.W1.get(), 
                    b1=self.b1.get(), 
                    W2=self.W2.get(), 
                    b2=self.b2.get())
        logging.info(f"Model saved to {file_path}")

    def load(self, file_path):
        data = np.load(file_path)
        self.W1 = cp.array(data['W1'])
        self.b1 = cp.array(data['b1'])
        self.W2 = cp.array(data['W2'])
        self.b2 = cp.array(data['b2'])
        logging.info(f"Model loaded from {file_path}")
        
class Config:
    EPOCHS = 100
    BATCH_SIZE = pow(2, 4)
    NUM_SAMPLES = pow(2, 14)
    LEARNING_RATE = 0.1
    MIN_RANGE = 2
    MAX_RANGE = 2
    HIDDEN_SIZES = range(MIN_RANGE, MAX_RANGE + 1)
    ROUNDS = 30
    PATIENCE = int(EPOCHS*0.5)
    def __str__(self):
        return (
            f"Config:\n"
            f"  LEARNING_RATE={self.LEARNING_RATE}\n"
            f"  EPOCHS={self.EPOCHS}\n"
            f"  BATCH_SIZE={self.BATCH_SIZE}\n"
            f"  NUM_SAMPLES={self.NUM_SAMPLES}\n"
            f"  MIN_RANGE={self.MIN_RANGE}\n"
            f"  MAX_RANGE={self.MAX_RANGE}\n"
            f"  HIDDEN_SIZES={list(self.HIDDEN_SIZES)}\n"
            f"  ROUNDS={self.ROUNDS}\n"
            f"  PATIENCE={self.PATIENCE}\n"
            )
        
def generate_data(num_samples=10000):
    np.random.seed(42)
    # 生成隨機數據，分別從兩個區間選擇
    X = np.zeros((num_samples, 2))
    for i in range(num_samples):
        for j in range(2):
            X[i, j] = np.random.choice([np.random.uniform(-0.5, 0.2), np.random.uniform(0.8, 1.5)])
    # 將數值轉換為0或1
    X_binarized = (X > 0.5).astype(int)
    # 計算 XOR
    y = np.bitwise_xor(X_binarized[:, 0], X_binarized[:, 1]).reshape(-1, 1)
    
    return X, y
     
def check_and_save_data(csv_path, num_samples):
    if os.path.exists(csv_path):
        logging.info(f"Loading existing dataset from {csv_path}")
        data = pd.read_csv(csv_path)
        X = data[['x1', 'x2']].values
        y = data['y'].values.reshape(-1, 1)
    else:
        logging.info(f"No existing dataset found. Generating new data...")
        X, y = generate_data(num_samples)
        pd.DataFrame({'x1': X[:, 0], 'x2': X[:, 1], 'y': y.flatten()}).to_csv(csv_path, index=False)
        logging.info(f"Dataset saved to {csv_path}")
    return X, y

config = Config()
X, y = check_and_save_data('dataset.csv', config.NUM_SAMPLES)
train_size = int(0.8 * X.shape[0])
X_train, X_test = X[:train_size], X[train_size:]
y_train, y_test = y[:train_size], y[train_size:]

scaler_X_0, scaler_X_1 = StandardScaler(), StandardScaler()
X_train_0 = X_train[:, 0].reshape(-1, 1)
X_train_1 = X_train[:, 1].reshape(-1, 1)
X_train = np.hstack((X_train_0, X_train_1))

X_test_0 = X_test[:, 0].reshape(-1, 1)
X_test_1 = X_test[:, 1].reshape(-1, 1)
X_test = np.hstack((X_test_0, X_test_1))

y_train = y_train.reshape(-1, 1)
y_test = y_test.reshape(-1, 1)

X_train_T = X_train.T
y_train_T = y_train.reshape(1, -1)

X_train = cp.array(X_train.T, dtype=cp.float32)
X_test = cp.array(X_test.T, dtype=cp.float32)
y_train = cp.array(y_train.T, dtype=cp.float32)
y_test = cp.array(y_test.T, dtype=cp.float32)

results = []
best_val_model, best_train_model = None, None
best_val_loss, best_train_loss = float('inf'), float('inf')
best_val_hidden_size, best_train_hidden_size = None, None
best_val_loss_history, best_train_loss_history = [], []
best_parameters_history=[]
logging.info(config)
for hidden_size in config.HIDDEN_SIZES:
    logging.info(f'----Hidden_size {hidden_size}:')
    losses = []
    for _ in range(config.ROUNDS):
        logging.info(f'Round({_+1}/{config.ROUNDS})')
        nn = ShallowNeuralNetwork(input_size=2, hidden_size=hidden_size, output_size=1, learning_rate=config.LEARNING_RATE)
        loss_history, val_losses, epoch, parameters_history  = nn.train(X_train, y_train, X_test, y_test, epochs=config.EPOCHS, batch_size=config.BATCH_SIZE, patience=config.PATIENCE)
        y_pred = nn.predict(X_test)
        loss = cp.sqrt(cp.mean(cp.square(y_pred - y_test)))
        losses.append(min(val_losses))
        if epoch == 0:
            logging.info(f'>>training completed\t\t| train loss={min(loss_history)}, val loss={min(val_losses)}')
        else:
            logging.info(f'>>early stopped at epoch {epoch+1}\t| train loss={min(loss_history)}, val loss={min(val_losses)}')

        if min(val_losses) < best_val_loss:
            best_val_loss = min(val_losses)
            best_val_model = nn
            best_val_hidden_size = hidden_size
            best_val_loss_history = val_losses
            best_val_model.save('best_val_model.npz')  # 保存最佳驗證模型
            best_parameters_history = parameters_history 
        if min(loss_history) < best_train_loss:
            best_train_loss = min(loss_history)
            best_train_model = nn
            best_train_hidden_size = hidden_size
            best_train_loss_history = loss_history
            best_train_model.save('best_train_model.npz')  # 保存最佳訓練模型
    results.append(losses)
    logging.info(f'#目前最低損失: train={best_train_loss}, val={best_val_loss}')
    logging.info(f'#目前最佳隱藏層神經元數量: train={best_train_hidden_size}, val={best_val_hidden_size}')
    logging.info(f'#目前最佳參數:\n-train:{best_train_model}\n-val:{best_val_model}\n')
logging.info(f'----最佳隱藏層神經元數量: train={best_train_hidden_size}, val={best_val_hidden_size}')

best_val_model.forward(X_test)
y_pred = best_val_model.output
y_test_inv = y_test.get().reshape(-1, 1).flatten()
y_pred_inv = y_pred.get().reshape(-1, 1).flatten()

plt.figure(figsize=(6, 6))
plt.scatter(y_test_inv, y_pred_inv, alpha=0.6, label='Predicted vs Actual')
plt.plot([min(y_test_inv), max(y_test_inv)], [min(y_test_inv), max(y_test_inv)], 'r--', label='Ideal Prediction')
plt.xlabel('Actual Values')
plt.ylabel('Predicted Values')
plt.title('Actual vs. Predicted Values with Best Hidden Layer Size')
plt.legend()
plt.savefig('Actual vs Predicted Values with Best Hidden Layer Size.png')

plt.figure(figsize=(12, 6))
plt.plot(best_val_loss_history)
plt.xlabel('Epoch')
plt.ylabel('Loss')
plt.title(f'Learning Curve (Hidden Size: {best_val_hidden_size})')
plt.savefig('Learning Curve (val).png')

plt.figure(figsize=(12, 6))
plt.plot(best_train_loss_history)
plt.xlabel('Epoch')
plt.ylabel('Loss')
plt.title(f'Learning Curve (Hidden Size: {best_train_hidden_size})')
plt.savefig('Learning Curve (train).png')

errors = y_pred_inv - y_test_inv
plt.figure(figsize=(12, 6))
plt.hist(errors, bins=50)
plt.xlabel('Error')
plt.ylabel('Frequency')
plt.title(f'Error Histogram (Hidden Size: {best_val_hidden_size})')
plt.savefig('Error Histogram (val).png')


def plot_decision_boundary(parameters_history, X, y):
    fig, ax = plt.subplots()
    
    def animate(i):
        ax.clear()
        W1, b1, W2, b2 = parameters_history[i]
        
        # 繪製數據點
        ax.scatter(X[:, 0], X[:, 1], c=y.flatten(), cmap='coolwarm', s=20, edgecolor='k')
        
        # 繪製分類線
        x_values = np.linspace(X[:, 0].min()-0.5, X[:, 0].max()+0.5, 200)
        y_values = np.linspace(X[:, 1].min()-0.5, X[:, 1].max()+0.5, 200)
        x_grid, y_grid = np.meshgrid(x_values, y_values)
        z = np.dot(W2, np.tanh(np.dot(W1, np.c_[x_grid.ravel(), y_grid.ravel()].T) + b1)) + b2
        z = z.reshape(x_grid.shape)
        ax.contourf(x_grid, y_grid, z, levels=np.linspace(z.min(), z.max(), 3), cmap='coolwarm', alpha=0.5)
        ax.set_title(f'Epoch: {i + 1}')
    
    ani = animation.FuncAnimation(fig, animate, frames=len(parameters_history), interval=200)
    ani.save('decision_boundary_evolution.mp4', writer='ffmpeg')

plot_decision_boundary(best_parameters_history, X_test.get().T, y_test.get())