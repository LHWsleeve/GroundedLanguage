import os,random,sys,gzip
sys.path.append(".")

from TFLibraries.Embeddings import Embedding
from TFLibraries.Layer import Layers
from TFLibraries.Ops import *
from Priors.Evaluation import Eval
import tensorflow as tf
import numpy as np
np.set_printoptions(threshold=np.nan)
Layer = Layers()

""" Parameters """
random.seed(20160408)
batch_size = 512
maxlength = 40
filters = int(sys.argv[1])
hiddendim = 100
num_epochs = 12

rep_dim = 32
offset = rep_dim/2 -1
block_size = 0.1528
space_size = 3.0
unit_size = space_size / rep_dim

Directory = '/home/ybisk/GroundedLanguage'
TrainData = 'Priors/Train.%d.L1.LangAndBlank.20.npz' % rep_dim
EvalData = 'Priors/Dev.%d.L1.Lang.20.npz' % rep_dim
RawEval = 'Priors/WithText/Dev.mat.gz'
#EvalData = 'Priors/Test.Lang.20.npz'
#RawEval = 'Priors/WithText/Test.mat.gz'


""" Helper Functions """

""" Create Batches for Training """
indices = []
def gen_batch_L(size, Wi, U, L, Wj):
  """
  Generate a batch for training with language data
  """
  global indices
  if len(indices) < size:
    # Randomly reorder the data
    v = range(len(Wi))
    random.shuffle(v)
    indices.extend(v)
  r = indices[:size]
  indices = indices[size:]
  return Wi[r], Wj[r], U[r],  L[r]
  ## Create zeros for world experiment
  ##Z = np.zeros((size,18,18,20))
  #return Z, Wj[r], U[r],  L[r]
  ## Create zeros for language experiment
  #Z = np.zeros((size,40))
  #return Wi[r], Wj[r], Z,  L[r]

Bindices = []
def gen_batch_B(size, Wi, U, L, Wj):
  """
  Generate a batch for training with unlabeled priors data
  """
  global Bindices
  if len(Bindices) < size:
    # Randomly reorder the data
    v = range(len(Wi))
    random.shuffle(v)
    Bindices.extend(v)
  r = Bindices[:size]
  Bindices = Bindices[size:]
  return Wi[r], Wj[r], U[r], L[r]

""" Data processing """

def process(U, maxlength=40, vocabsize=10000):
  """
  Need to return:  Utterenaces, lengths, vocabsize
  """
  max_vocab = 0
  lengths = []
  filtered = np.zeros(shape=[len(U), maxlength], dtype=np.int32)
  for i in range(len(U)):
    utterance = U[i]
    lengths.append(len(utterance))
    for j in range(min(len(utterance), maxlength)):
      if utterance[j] > vocabsize:
        filtered[i][j] = 1
      else:
        filtered[i][j] = utterance[j]
    max_vocab = max(max_vocab, max(utterance))
  return filtered, np.array(lengths, dtype=np.int32), max_vocab


""" Read Data """

os.chdir(Directory)
print("Running from ", os.getcwd())
## Regular + Blank (B)
Data = np.load(TrainData)
Wi, U, Wj = Data["Lang_Wi"], Data["Lang_U"], Data["Lang_Wj"]
BWi, BU, BWj = Data["Blank_Wi"], Data["Blank_U"], Data["Blank_Wj"]
U, lens, vocabsize = process(U, maxlength)
BU, Blens, Bvocabsize = process(BU, maxlength)
## Labeled
Eval_Data = np.load(EvalData)
DWi, DU, DWj = Eval_Data["Lang_Wi"], Eval_Data["Lang_U"], Eval_Data["Lang_Wj"]
DU, Dlens, vocabsize = process(DU, maxlength, vocabsize)

# Read in the actual eval (x,y,z) data
F = gzip.open(RawEval, 'r')
real_dev = np.array([map(float, line.split()[:120]) for line in F])
# item with biggest change
real_dev_id = np.argmax(np.abs(real_dev[:,:60] - real_dev[:,60:]), axis=1)/3

""" Model Definition """

## Inputs        #[batch, height, width, depth]
cur_world = tf.placeholder(tf.float32, [batch_size, rep_dim, rep_dim, 20], name="CurWorld")
next_world = tf.placeholder(tf.float32, [batch_size, rep_dim*rep_dim], name="NextWorld")
## Language
inputs = tf.placeholder(tf.int32, [batch_size, maxlength], name="Utterance")
lengths = tf.placeholder(tf.int32, [batch_size], name="Lengths")

final_size = rep_dim - 5*2
## weights && Convolutions
W = {
  'cl1': Layer.convW([3, 3, 20, filters]),
  'cl2': Layer.convW([3, 3, filters, filters]),
  'cl3': Layer.convW([3, 3, filters, filters]),
  'cl4': Layer.convW([3, 3, filters, filters]),
  'cl5': Layer.convW([3, 3, filters, filters]),
  'out': Layer.W(final_size*final_size*filters + 2*hiddendim, rep_dim*rep_dim)
}

B = {
  'cb1': Layer.b(filters, init='Normal'),
  'cb2': Layer.b(filters, init='Normal'),
  'cb3': Layer.b(filters, init='Normal'),
  'cb4': Layer.b(filters, init='Normal'),
  'cb5': Layer.b(filters, init='Normal'),
  'out': Layer.b(rep_dim*rep_dim)
}

# Define embeddings matrix
embeddings = Embedding(vocabsize, one_hot=False, embedding_size=hiddendim)

# RNN
dropout = 0.75
lstm = tf.nn.rnn_cell.LSTMCell(hiddendim,
               initializer=tf.contrib.layers.xavier_initializer(seed=20160501))
lstm = tf.nn.rnn_cell.DropoutWrapper(lstm, output_keep_prob=dropout)

# Encode from 18x18 to 12x12
l1 = conv2d('l1', cur_world, W['cl1'], B['cb1'], padding='VALID') # -> 32->30  18->16
l2 = conv2d('l2', l1, W['cl2'], B['cb2'], padding='VALID')        # -> 30-28   16->14
l3 = conv2d('l3', l2, W['cl3'], B['cb3'], padding='VALID')        # -> 28->26  14->12
l4 = conv2d('l4', l3, W['cl4'], B['cb4'], padding='VALID')        # -> 26->24  12->10
l5 = conv2d('l5', l4, W['cl5'], B['cb5'], padding='VALID')        # -> 24->22  10->8

outputs, fstate = tf.nn.dynamic_rnn(lstm, embeddings.lookup(inputs), 
                                    sequence_length=lengths,
                                    dtype=tf.float32)

# Concatenate RNN output to CNN representation
logits = tf.matmul(
          tf.concat(1, [fstate,
            tf.reshape(l5, [batch_size,final_size*final_size*filters])]),
        W['out']) + B['out']
correct_prediction = tf.equal(tf.argmax(logits,1), tf.argmax(next_world,1))
loss = tf.reduce_mean(tf.nn.softmax_cross_entropy_with_logits(logits,next_world))

optimizer = tf.train.AdamOptimizer()
train_op = optimizer.minimize(loss)

sess = tf.Session()
sess.run(tf.initialize_all_variables())
total_loss = 0.0

ratio = 1.0

eval = Eval(sess, rep_dim, unit_size, space_size, batch_size, cur_world,
            next_world, inputs, lengths, logits, correct_prediction)

def run_step((batch_Wi, batch_Wj, batch_U, batch_L)):
  feed_dict = {cur_world: batch_Wi, next_world: batch_Wj,
               inputs: batch_U, lengths: batch_L}
  loss_val, t_op = sess.run([loss, train_op], feed_dict)
  return loss_val

discrete = []
real = []

for epoch in range(num_epochs):
  for step in range(BWi.shape[0]/batch_size):    ## Does not make use of full prior data this way
    total_loss += run_step(gen_batch_B(batch_size, BWi, BU, Blens, BWj))
  discrete.append(eval.SMeval(DWi, DU, Dlens, DWj))
  real.append(eval.real_eval(DWi, DU, Dlens, DWj, real_dev, real_dev_id))
  print("Iter %3d  Ratio %-6.4f  Loss %-8.3f   Eval  %-6.3f  %5.3f  %5.3f  G: %5.3f %5.3f" %
       (epoch, ratio, total_loss, discrete[-1], real[-1][0], real[-1][1], real[-1][2], real[-1][3]))
  total_loss = 0
    #ratio = 1.0 - epoch/25.0
print "Convereged on Priors"


for epoch in range(num_epochs):
  for step in range(Wi.shape[0]/batch_size):
    total_loss += run_step(gen_batch_L(batch_size, Wi, U, lens, Wj))
  discrete.append(eval.SMeval(DWi, DU, Dlens, DWj))
  real.append(eval.real_eval(DWi, DU, Dlens, DWj, real_dev, real_dev_id))
  print("Iter %3d  Ratio %-6.4f  Loss %-10f   Eval  %-6.3f  %5.3f  %5.3f  G: %5.3f %5.3f" %
        (epoch, ratio, total_loss, discrete[-1], real[-1][0], real[-1][1], real[-1][2], real[-1][3]))
  total_loss = 0
print "Converged on Language"

print "Grid v XYZ correlation: %5.3f %5.3f" % (
  pearson([r[0] for r in real], discrete), pearson([r[1] for r in real], discrete))

"""
 Print images showing the predictions of the model
"""

def collapse(F):
  M = np.zeros((rep_dim, rep_dim))
  for i in range(rep_dim):
    for j in range(rep_dim):
      if np.amax(F[i][j]) > 0:
          M[i][j] = 1
  return M

s = np.array(range(batch_size))
feed_dict = {cur_world: DWi[s], next_world: DWj[s],
             inputs: DU[s], lengths: Dlens[s]}
final = sess.run(logits, feed_dict)
for i in range(batch_size):
  # Show the final prediction confidences
  eval.createImage("images/P_%d_%d.bmp" % (epoch, i),
      collapse(DWi[s][i]),
      np.reshape(DWj[s], (batch_size,rep_dim,rep_dim))[i],
      np.reshape(final, (batch_size,rep_dim,rep_dim))[i], rep_dim)


