#! /usr/bin/python3

import sys
import random
import time
import math
import gym
import numpy as np
from itertools import chain
from stable_baselines3 import PPO
from stable_baselines3.common.vec_env import DummyVecEnv, SubprocVecEnv
from stable_baselines3.common.env_util import make_vec_env
from stable_baselines3.common.torch_layers import BaseFeaturesExtractor
import torch as th
import torch.nn as nn
import torch.optim as optim

class KongmingChessEnv(gym.Env):
    def __init__(self, rand=False):
        self.board = np.zeros((7, 7), dtype=np.uint8) # 0表示未翻牌,1表示焦点位置,2表示候选点,3表示翻牌.4表示不可点击区域,
        for x in chain(range(0,2), range(5, 7)):
          for y in chain(range(0, 2), range(5, 7)):
            self.board[x][y] = 4 # 不可点击区域.
        self.reset(rand)
        self.observation_space = gym.spaces.Box(low=0, high=255, shape=(7, 7), dtype=np.uint8) # TODO: 是否需要修改为离散空间?

    def getObservationSpace(self):
        return self.observation_space

    def getTotalReward(self):
        return self.totalReward

    def reset(self, rand=False):
        for x in range(0, 7):
          for y in range(0, 7):
            if (x < 2 or x >= 5) and (y < 2 or y >= 5):
              continue
            self.board[x][y] = 0
        self.focus = None
        self.candidates = None
        self.steps = 0
        self.done = False
        self.totalReward = 0

        if rand == False:
          self.board[3][3] = 3
          self.remainings = 32
        else:
          # 产生1到31个随机位置掀开，并确保游戏没结束.
          while True:
              for x in range(0, 7):
                  for y in range(0, 7):
                      if (x < 2 or x >= 5) and (y < 2 or y >= 5):
                          continue
                      self.board[x][y] = 0

              numOpen = random.randint(1, 31)
              i = numOpen
              while i > 0:
                  if numOpen == 1:
                      coord = 16
                  else:
                      coord = random.randint(0, 32)
                  if coord >= 0 and coord <= 5:
                      x = (coord % 3) + 2
                      y = (coord // 3)
                  elif coord >= 6 and coord <= 26:
                      y = ((coord - 6) // 7) + 2
                      x = ((coord - 6) % 7)
                  elif coord >= 27 and coord <= 32:
                      x = ((coord - 27) % 3) + 2
                      y = ((coord - 27) // 3) + 5
                  if self.board[x][y] == 0:
                      i -= 1
                      self.board[x][y] = 3
              self.remainings = 33 - numOpen
              if not self.check_over():
                  break
        return self.board

    def getFinalReward(self):
      return 0
      if self.remainings == 1 and self.board[3][3] == 0:
        return math.pow(10, 7)
      else:
        return math.pow(10, 7 -  self.remainings)

    def check_over(self):
      if self.remainings == 1:
        return True

      # 找不到可以跳转的节点对
      for x in range(0, 7):
        for y in range(0, 7):
          if (x < 2 or x >= 5) and (y < 2 or y >= 5):
            continue
          if self.board[x][y] == 2 or self.board[x][y] == 3:
            continue
          if x + 2 < 7 and (self.board[x + 1][y] == 0 or self.board[x + 1][y] == 1) and (self.board[x + 2][y] == 2 or self.board[x + 2][y] == 3):
            return False
          if x - 2 >= 0 and (self.board[x - 1][y] == 0 or self.board[x - 1][y] == 1) and (self.board[x - 2][y] == 2 or self.board[x - 2][y] == 3):
            return False
          if y + 2 < 7 and (self.board[x][y + 1] == 0 or self.board[x][y + 1] == 1) and (self.board[x][y + 2] == 2 or self.board[x][y + 2] == 3):
            return False
          if y - 2 >= 0 and (self.board[x][y - 1] == 0 or self.board[x][y - 1] == 1) and (self.board[x][y - 2] == 2 or self.board[x][y - 2] == 3):
            return False
      return True


    def getRemainings(self):
        return self.remainings

    def render(self):
        for i in range(0, 7):
            s = ""
            for j in range(0, 7):
              s += str(self.board[i][j])
              s += ","
            print(s)

    def getFocus(self):
        return self.focus

    def avgDelta(self, delta):
        return delta
        formerTotal = self.totalReward - delta
        formerSteps = self.steps - 1
        if formerSteps == 0:
            return float(self.totalReward) / self.steps
        else:
            return float(self.totalReward) / self.steps - float(formerTotal) / formerSteps

    def step(self, action):
#      if self.remainings <= 5:
#          print("Nice Stepping:", self.remainings, self.totalReward, self.steps, self.totalReward / float(self.steps))
      self.steps += 1
      x = action % 7
      y = action // 7
      if self.board[x][y] == 4: # 不可点击区域,惩罚
        self.totalReward -= 100
        return self.board, self.avgDelta(-100), self.done, {}
     
      if self.focus == None:
        if self.board[x][y] == 3: # 当前无焦点，却点到空格子, 惩罚
          self.totalReward -= 100
          return self.board, self.avgDelta(-100), self.done, {}

        # 逐个判断候选选点
        candidates = []
        midpoints = []
        if y - 2 >= 0 and self.board[x][y -1] == 0 and self.board[x][y - 2] == 3:
          candidates.append((x, y - 2))
          midpoints.append((x, y - 1))
        if y + 2 < 7 and self.board[x][y + 1] == 0 and self.board[x][y + 2] == 3:
          candidates.append((x, y + 2))
          midpoints.append((x, y + 1))
        if x - 2 >= 0 and self.board[x - 1][y] == 0 and self.board[x - 2][y] == 3:
          candidates.append((x - 2, y))
          midpoints.append((x - 1, y))
        if x + 2 < 7 and self.board[x + 1][y] == 0 and self.board[x + 2][y] == 3:
          candidates.append((x + 2, y))
          midpoints.append((x + 1, y))

        if len(candidates) == 0: # 点了不当的焦点，惩罚
          self.totalReward -= 100
          return self.board, self.avgDelta(-100), self.done, {}

        # 如果只有一个候选节点，则直接跳.
        if len(candidates) == 1:
          self.board[x][y] = 3
          self.board[midpoints[0][0]][midpoints[0][1]] = 3
          self.board[candidates[0][0]][candidates[0][1]] = 0
          self.remainings -= 1
          self.done = self.check_over()
          self.totalReward += 0.5
          if self.done == True:
            self.totalReward += self.getFinalReward()
            return self.board, self.avgDelta(0.5 + self.getFinalReward()), self.done, {}
          return self.board, self.avgDelta(0.5), self.done, {}   

        self.focus = (x, y)
        self.candidates = candidates
        self.board[x][y] = 1
        for xx, yy in candidates:
          self.board[xx][yy] = 2
        return self.board, self.avgDelta(0), self.done, {}

      # 已经有跳转起点了.
      # 判断点击的是否为候选节点
      if self.board[x][y] != 2:
        self.board[self.focus[0]][self.focus[1]] = 0
        self.focus = None
        for xx, yy in self.candidates:
          self.board[xx][yy] = 3
        self.candidates = None
        self.totalReward -= 100
        return self.board, self.avgDelta(-100), self.done, {}  # 点了非候选节点，惩罚

      if x == self.focus[0]:
        midX = x
        if y == self.focus[1] + 2:
          midY = y - 1
        elif y == self.focus[1] - 2:
          midY = y + 1
      elif y == self.focus[1]:
        midY = y
        if x == self.focus[0] + 2:
          midX = x - 1
        elif x == self.focus[0] - 2:
          midX = x + 1

      self.remainings -= 1
      self.board[x][y] = 0
      self.board[self.focus[0]][self.focus[1]] = 3
      self.board[midX][midY] = 3
      self.focus = None
      for xx, yy in self.candidates:
        if xx == x and yy == y:
          continue
        self.board[xx][yy] = 3
      self.candidates = None
      self.done = self.check_over()
      if self.done == True:
        self.totalReward += 1
        self.totalReward += self.getFinalReward()
        return self.board, self.avgDelta(1 + self.getFinalReward()), True, {}
      self.totalReward += 1
      return self.board, self.avgDelta(1), self.done, {}

def make_env():
        return KongmingChessEnv()

def predict_proba(model, state):
  state = np.transpose(state)
  input_tensor = th.from_numpy(state.reshape((1, 1, 7, 7))).float()
  probs = th.softmax(model(input_tensor), dim=-1)
  max_prob, predicted_class = th.max(probs, dim=1)
  max_prob = max_prob[0]
  predicred_class = predicted_class[0]
  probs_np = probs.detach().numpy()
  print(probs_np)
  sys.stdout.flush()
  probs = []
  s = 0.0
  for i in range(0, 49):
      probs.append(math.exp(probs_np[0][i]))
      s += probs[i]
  s /= 100
  for i in range(0, 49):
      probs[i] /= s
  for i in range(0, 7):
      print('{:.2f}\t{:.2f}\t{:.2f}\t{:.2f}\t{:.2f}\t{:.2f}\t{:.2f}'.format(probs[7 * i], probs[7 * i + 1], probs[7 * i + 2], probs[7 * i + 3], probs[7 * i + 4], probs[7 * i + 5], probs[7 * i + 6]), sep='\t')
  return predicted_class.item(), max_prob.item(), probs

def roulette_wheel_selection(a):
  # 计算数组中所有元素的和
  S = sum(a)
  # 计算每个元素的概率值
  p = [x/S for x in a]
  # 生成一个随机数
  r = random.random()
  # 依次累加每个元素的概率值，直到累加和大于随机数为止
  s = 0
  for i in range(len(p)):
    s += p[i]
    if s >= r:
      return i, p[i]
  # 如果所有元素的概率值之和小于随机数，返回最后一个元素
  return len(a) - 1, p[-1]

class PolicyGradientAgent:
    def __init__(self, env, learning_rate=0.01, gamma=0.0):
        self.env = env
        self.learning_rate = learning_rate
        self.gamma = gamma
        self.model = self.build_model()

    def build_model(self):
      cnn = nn.Sequential(
        nn.Conv2d(1, 16, kernel_size=3, stride=1, padding=0),
        nn.ReLU(),
        nn.Conv2d(16, 32, kernel_size=3, stride=1, padding=0),
        nn.ReLU(),
        nn.Flatten(),
      )

      # Compute shape by doing one forward pass
      with th.no_grad():
        n_flatten = cnn(
        th.from_numpy(np.random.randint(0, 256, size=(1, 1, 7, 7), dtype=np.uint8)).float()
      ).shape[1]

      hidden_size = 512
      model = nn.Sequential(
              nn.Flatten(),
              nn.Linear(49, hidden_size),
              nn.ReLU(),
              nn.Dropout(0.2),
              nn.Linear(hidden_size, hidden_size),
              nn.ReLU(),
              nn.Dropout(0.2),
              nn.Linear(hidden_size, 49)
      )
      baseline_net = nn.Sequential(
              nn.Flatten(),
              nn.Linear(49, hidden_size),
              nn.ReLU(),
              nn.Dropout(0.2),
              nn.Linear(hidden_size, hidden_size),
              nn.ReLU(),
              nn.Dropout(0.2),
              nn.Linear(hidden_size, 1)
      )
      optimizer = optim.Adam(model.parameters(), lr=0.03, weight_decay=0.001)
      baseline_optimizer = optim.Adam(baseline_net.parameters(), lr=0.03, weight_decay=0.001)
      return model, baseline_net, optimizer, baseline_optimizer

    def choose_action(self, state):
        state = np.transpose(state)
        input_tensor = th.from_numpy(state.reshape((1, 1, 7, 7))).float()
        probabilities = th.softmax(self.model[0](input_tensor), dim=1)
        action = th.multinomial(probabilities, num_samples=1).item()
        return action

    def train(self, episode_states, episode_actions, episode_rewards):
        #print(episode_states, episode_actions, episode_rewards)
        discounted_rewards = self.discount_rewards(episode_rewards)
        episode_actions = th.tensor(episode_actions, dtype=th.int64)
        episode_states = th.stack([th.from_numpy(x) for x in episode_states])
        episode_states = episode_states.unsqueeze(1).float()
        discounted_rewards = th.tensor(discounted_rewards, dtype=th.float32)
        optimizer = self.model[2]
        baseline_optimizer = self.model[3]
        # 计算损失函数,损失函数为总期望回报.
        action_probs = th.softmax(self.model[0](episode_states), dim=1)
        actions_one_hot = nn.functional.one_hot(episode_actions, 49)
        log_probs = th.sum(action_probs * actions_one_hot, dim=1)
        baseline = self.model[1](episode_states)
        loss = -th.sum(log_probs * (discounted_rewards - baseline.detach()))
        #loss = -th.sum(log_probs * discounted_rewards)
        #print("Action Probs: ", action_probs)
        #print("Actions Onehot: ", actions_one_hot[0])
        #print("Probs: ", log_probs)
        #print("Discounted rewards: ", discounted_rewards)
        #print("Loss: ", loss.item())
        #logits = self.model[0](episode_states)
        #loss = criterion(logits, episode_actions)
        #print(baseline)
        #xxx
        optimizer.zero_grad()
        loss.backward()
        optimizer.step()

        baseline_loss = th.mean((discounted_rewards.detach() - baseline) ** 2)
        baseline_optimizer.zero_grad()
        baseline_loss.backward()
        baseline_optimizer.step()
        grads = {}
        for name, param in self.model[0].named_parameters():
          if param.grad is not None:
            grads[name] = param.grad.norm()
        baseline_grads = {}
        for name, param in self.model[1].named_parameters():
          if param.grad is not None:
            baseline_grads[name] = param.grad.norm()
        return loss.item(), baseline_loss.item(), grads, baseline_grads

    # 折扣奖励，从最后一个时间步开始，计算每个时间步的折扣奖励
    def discount_rewards(self, rewards):
        discounted_rewards = np.zeros_like(rewards)
        running_total = 0
        for t in reversed(range(len(rewards))):
            running_total = running_total * self.gamma + rewards[t]
            discounted_rewards[t] = running_total
        return discounted_rewards

    def getModel(self):
        return self.model[0]

if __name__ == '__main__':
    env = KongmingChessEnv()
    agent = PolicyGradientAgent(env)

    totalsteps = 100000
    print("开始训练，总训练步数：", totalsteps, "\n")
    for episode in range(totalsteps):
        state = env.reset()
        episode_states, episode_actions, episode_rewards = [], [], []
        done = False
        i = 0
        while i < 5000 and not done:
            action = agent.choose_action(state)
            next_state, reward, done, info = env.step(action)
            episode_states.append(state)
            episode_actions.append(action)
            episode_rewards.append(reward)
            state = next_state
            i += 1
        loss, baseline_loss, grads, baseline_grads = agent.train(episode_states, episode_actions, episode_rewards)
        if ((episode % 50) == 0):
          #print("Process:", episode, " / ", totalsteps, "loss=", loss, "baseline_loss=", baseline_loss)
          print("\033[FProcess:", episode, " / ", totalsteps, "loss=", loss, "baseline_loss=", baseline_loss, "steps=", i, "remainings=", env.getRemainings(), "grads=", grads, "baselinegrads=", baseline_grads)
          sys.stdout.flush()
    model = agent.getModel()
    input("模型训练结束，请按任意键开始走棋!")
    done = False
    obs = env.reset(False)
    action_set = set([])
    action_set_focus = []
    for x in range(0, 7):
      for y in range(0, 7):
        action_set_focus.append(set([]))
  #  obs, reward, done, info = env.step(22)
  #  print(reward)
  #  print(obs)
    steps = 0
    while not env.check_over():
      preFocus = env.getFocus()
      # 获取动作预测
      action, prob, probs = predict_proba(model, obs)
      maxarg = True
      if preFocus == None:
          testSet = action_set
      else:
          testSet = action_set_focus[preFocus[1] * 7 + preFocus[0]]
      while action in testSet:
        #action, prob = model.predict(obs, deterministic=False)
        action, prob = roulette_wheel_selection(probs)
        maxarg = False

      print(action, prob, maxarg)
      obs, reward, done, info = env.step(action)
      if reward < 0:
        if preFocus == None:
          action_set.add(action)
        else:
          action_set_focus[preFocus[1] * 7 + preFocus[0]].add(action)
      elif reward > 0:
        action_set = set([])
        action_set_focus = []
        for x in range(0, 7):
            for y in range(0, 7):
                action_set_focus.append(set([]))
      steps += 1
      print('Action: ', action % 7, action // 7)
      print('Reward: ', reward)
      print('Remainings: ', env.getRemainings())
      print('Observation: ')
      env.render()
      print('Steps: ', steps)
      print('TotalReward: ', env.getTotalReward())
      sys.stdout.flush()
      lastAction = action
      time.sleep(0.3)
