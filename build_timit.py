import os
import re
import sys
import time
import h5py
import pickle
import torch
import argparse
import numpy as np
from math import ceil
from tqdm import tqdm
from glob import glob
import soundfile as sf
import librosa

class TimitDictionary():
    def __init__(self, dataset):

        # parse dataset for phonemes
        self.parse_dataset_phonemes(dataset)

        # assign phonemes to dictionary
        self.idx_phonemes = {key: value for key, value in enumerate(self.phonemes)}
        self.phonemes_idx = {value: key for key, value in self.idx_phonemes.items()}

        # combines phonemes that are interchangably used in dictionary 
        self.fold_phonemes()

        # renumber phonemes from 0 to number of phonemes
        self.renumber_phonemes()

        # parse dictionary for phonemes
#        self.dict_file = dict_file
#        self.parse_timit_dict()

    def renumber_phonemes(self):
        numbers = []

        # find unique numbers
        for _, value in self.phonemes_idx.items():
            if value not in numbers:
                numbers.append(value)

        # reassign numbers starting at 0
        for i, number in enumerate(numbers):
            for key in self.phonemes_idx:
                if self.phonemes_idx[key] == number:
                    self.phonemes_idx[key] = i

        # new number of phonemes after folding
        self.num_phonemes = len(numbers)

        # final numbering of folded phonemes
        for i in range(len(numbers)):
            print(f'{i}: ', end=' ')
            for key, value in self.phonemes_idx.items():
                if value == i:
                    print(key, end=' ')
            print()

    def parse_dataset_phonemes(self, dataset):
        all_phonemes = []
        print('Finding all phonemes in dataset')
        for phn_file in tqdm(glob(os.path.join(dataset, '**/*.PHN'), recursive=True)):
            phns = TimitDataLoader.extract_phonemes(phn_file)
            # last element is phonme name
            phns = np.array(phns)[:,-1]
            all_phonemes.extend(phns.tolist())

        self.phonemes = set(all_phonemes)
        self.num_phonemes = len(self.phonemes)

    def parse_timit_dict(self):
        phonemes = []
        # load phonemes for each word in dictionary 
        with open(self.dict_file, 'r') as f:
            for line in f.readlines():
                if line[0].isalpha():
                    line_phonemes = line.split('/')[1]
                    line_phonemes = re.sub(r'[0-9]+', '', line_phonemes).split(' ')
                    
                    phonemes.extend(line_phonemes)

        # remove duplicates
        phonemes = set(phonemes)
        self.num_phonemes = len(phonemes)

        # create look-up dictionaries for each phoneme
        self.idx_phonemes = {key: value for key, value in enumerate(phonemes)}
        self.phonemes_idx = {value: key for key, value in self.idx_phonemes.items()}

        # fold similar phonemes from: Speaker-indepented phone recognition using hidden Markov models.
        self.fold_phonmes()

    # combine phonemes that have similar usages throughout dictionary 
    def fold_phonemes(self):
        self.phonemes_idx['ih'] = self.phonemes_idx['ix']
        self.phonemes_idx['ah'] = self.phonemes_idx['ax']
        self.phonemes_idx['ax-h'] = self.phonemes_idx['ax']
        self.phonemes_idx['ux'] = self.phonemes_idx['uw']
        self.phonemes_idx['aa'] = self.phonemes_idx['ao']
        self.phonemes_idx['axr'] = self.phonemes_idx['er']
        self.phonemes_idx['el'] = self.phonemes_idx['l']
        self.phonemes_idx['em'] = self.phonemes_idx['m']
        self.phonemes_idx['en'] = self.phonemes_idx['n']
        self.phonemes_idx['nx'] = self.phonemes_idx['n']
        self.phonemes_idx['eng'] = self.phonemes_idx['ng']
        self.phonemes_idx['sh'] = self.phonemes_idx['zh']
        self.phonemes_idx['hv'] = self.phonemes_idx['hh']
        self.phonemes_idx['#h'] = self.phonemes_idx['h#']
        self.phonemes_idx['bcl'] = self.phonemes_idx['h#']
        self.phonemes_idx['pcl'] = self.phonemes_idx['h#']
        self.phonemes_idx['dcl'] = self.phonemes_idx['h#']
        self.phonemes_idx['tcl'] = self.phonemes_idx['h#']
        self.phonemes_idx['gcl'] = self.phonemes_idx['h#']
        self.phonemes_idx['kcl'] = self.phonemes_idx['h#']
        self.phonemes_idx['q'] = self.phonemes_idx['h#']
        self.phonemes_idx['epi'] = self.phonemes_idx['h#']
        self.phonemes_idx['pau'] = self.phonemes_idx['h#']

    def phn_to_idx(self, phn):
        return self.phonemes_idx[phn]

    def exists(self, phn):
        if phn in self.phonemes_idx.keys():
            return 1
        return 0

class TimitDataLoader():
    def __init__(self, root_dir=None, timit_dict=None, num_ffts=None, hop_length=None, num_mels=None, num_mfccs=None):

        # root directory to timit train and test data
        self.root_dir = root_dir

        # Phoneme dictionary
        self.timit_dict = timit_dict

        # audio parameters
        self.num_ffts = num_ffts
        self.hop_length = hop_length
        self.num_mels = num_mels
        self.num_mfccs = num_mfccs

    def load_from_wavs(self):
        # load data sets from raw data
        self.train_feats, self.train_phns = self.load_dataset(self.root_dir, 'TRAIN')
        self.test_feats, self.test_phns = self.load_dataset(self.root_dir, 'TEST')

    def load_from_h5(self, data_dir):
        self.train_feats, self.train_phns = self._load_from_h5(os.path.join(data_dir, 'Train.h5'))
        self.test_feats, self.test_phns = self._load_from_h5(os.path.join(data_dir, 'Test.h5'))

    def _load_from_h5(self, data_file):
        print(f'Loading data from {data_file}')
        features = {'mfccs': [], 'mels': [], 'dists': [], 'deltas': [], 'deltas2': []}
        with h5py.File(data_file, 'r') as h5f:
            features['mfccs'] = np.array(h5f['mfccs'])
            features['mels'] = np.array(h5f['mels'])
            features['dists'] = np.array(h5f['dists'])
            features['deltas'] = np.array(h5f['deltas'])
            features['deltas2'] = np.array(h5f['deltas2'])
            phns = np.array(h5f['phns'])
            return features, phns 

    def load_dataset(self, root_dir, dataset, max_len=3200):

        features = {'mfccs': [], 'mels': [], 'dists': [], 'deltas': [], 'deltas2': []}

        y = []
        print(f'Loading {dataset} dataset from source wavs')
        #max_size = 0
        for i, wav in enumerate(tqdm(glob(os.path.join(root_dir, dataset, '**/*WAV.wav'), recursive=True))):
            samples, sr = sf.read(wav)
            # load segment times / phonemes from file
            phns = self.extract_phonemes(wav.replace('.WAV.wav', '.PHN'))
            # find all segments except header and footer
            for phn in phns[2:-1]:
                start = int(phn[0])
                end = int(phn[1])
                length = end - start

                # skip spoken phonemes over a max length
                if length > max_len or not self.timit_dict.exists(phn[2]):
                    continue                      
                                                                
                # centered features in zero padded array of max length         
                diff = max_len - length
                pad = diff / 2
                seg = np.pad(samples[start:end], (int(pad), ceil(pad)), 'constant', constant_values=(0,0)) 

                # get features from segment
                mfccs, mels, dists, deltas, deltas2 = self.extract_features(seg, sr)
                features['mfccs'].append(mfccs)
                features['mels'].append(mels)
                features['dists'].append(dists)
                features['deltas'].append(deltas)
                features['deltas2'].append(deltas2)

                y.append(self.timit_dict.phn_to_idx(phn[2]))

        features['mfccs'] = np.array(features['mfccs'])
        features['mels'] = np.array(features['mels'])
        features['dists'] = np.array(features['dists'])
        features['deltas'] = np.array(features['deltas'])
        features['deltas2'] = np.array(features['deltas2'])
        print(f'loaded {i} wavs, with segment length {max_len}')
        
        return features, np.array(y)

    def extract_features(self, samples, sr):
        mels = librosa.feature.melspectrogram(samples,
                                     sr=sr,
                                     n_fft=self.num_ffts,
                                     hop_length=self.hop_length,
                                     n_mels=self.num_mels)

        mfccs = librosa.feature.mfcc(samples,
                                     sr=sr,
                                     n_fft=self.num_ffts,
                                     hop_length=self.hop_length,
                                     n_mels=self.num_mels,
                                     n_mfcc=self.num_mfccs+1)

        # drop first MFCC since there is little speech energy in that bin
        mfccs = mfccs[1:] 
        dists = self.mfcc_dist(mfccs)
        deltas  = librosa.feature.delta(mfccs, order=1)
        deltas2 = librosa.feature.delta(mfccs, order=2)
        return mfccs, mels, dists, deltas, deltas2

# From Phoneme Boundary Detection Using Learnable Segmental Features, Felix Kreuk et al.
    def mfcc_dist(self, mfcc):
        """mfcc_dist
        calc 4-dimensional dist features like in HTK
    
        :param mfcc:
        """
        d = []
        for i in range(2, 9, 2):
            pad = int(i/2)
            d_i = np.concatenate([np.zeros(pad), ((mfcc[:, i:] - mfcc[:, :-i]) ** 2).sum(0) ** 0.5, np.zeros(pad)], axis=0)
            d.append(d_i)
        return np.stack(d)

    @staticmethod
    def extract_phonemes(phn_file):
        with open(phn_file, 'r') as f:
            lines = f.read().splitlines()
            phonemes = [line.split(' ') for line in lines]

        return phonemes 

    def save_dataset_H5(self, out_dir='data'):
        # make output directory if it does not exist
        os.makedirs(out_dir, exist_ok=True)

        self.write_dataset(self.train_feats, self.train_phns, os.path.join(out_dir, 'Train.h5'))
        self.write_dataset(self.test_feats, self.test_phns, os.path.join(out_dir, 'Test.h5'))

    def write_dataset(self, features, phns, out_file):
        with h5py.File(out_file, 'w') as h5f:
            h5f.create_dataset('mfccs', data=features["mfccs"])
            h5f.create_dataset('mels', data=features["mels"])
            h5f.create_dataset('dists', data=features["dists"])
            h5f.create_dataset('deltas', data=features["deltas"])
            h5f.create_dataset('deltas2', data=features["deltas2"])
            h5f.create_dataset('phns', data=phns)

    def dataset_stats(self):
        print(f'Train MFCCs features -> {self.train_feats["mfccs"].shape}')
        print(f'Train Mels features -> {self.train_feats["mels"].shape}')
        print(f'Train Distances features -> {self.train_feats["dists"].shape}')
        print(f'Train Deltas features -> {self.train_feats["deltas"].shape}')
        print(f'Train 2nd Deltas features -> {self.train_feats["deltas2"].shape}')
        print(f'Train phonemes -> {self.train_phns.shape}')
        for feat in ['mfccs', 'mels', 'dists', 'deltas', 'deltas']:
            assert self.train_feats[feat].shape[0] == self.train_phns.shape[0], f"number labels don't macth number of examples for {feat}"

        print(f'Test MFCCs features -> {self.test_feats["mfccs"].shape}')
        print(f'Test Mels features -> {self.test_feats["mels"].shape}')
        print(f'Test Distances features -> {self.test_feats["dists"].shape}')
        print(f'Test Deltas features -> {self.test_feats["deltas"].shape}')
        print(f'Test 2nd Deltas features -> {self.test_feats["deltas2"].shape}')
        print(f'Test phonemes -> {self.test_phns.shape}')
        for feat in ['mfccs', 'mels', 'dists', 'deltas', 'deltas']:
            assert self.test_feats[feat].shape[0] == self.test_phns.shape[0], f"number labels don't macth number of examples for {feat}"

def main(args):
    start = time.time()

    # build timit dictionary from timit dictionary file
    timit_dict = TimitDictionary(args.timit_path)
    print(f'Number of phonemes in dictionary: {timit_dict.num_phonemes}')

    # create timit dataset object 
    timit_data = TimitDataLoader(args.timit_path, timit_dict, args.num_ffts, 
                                 args.hop_length, args.num_mels, args.num_mfccs)

    # load dataset from original source wavs
    timit_data.load_from_wavs()

    # show/verify sizes of datasets
    timit_data.dataset_stats()

    # save timit dataset to H5 files
    timit_data.save_dataset_H5(args.out_dir)

    # save timit dictionary object to file
    pickle.dump(timit_dict, open(os.path.join(args.out_dir, args.timit_dict_file),'wb'))
    print(f'Timit dictionary saved to {args.timit_dict_file}.')

    # load dataset from H5 files
    timit_data.load_from_h5(args.out_dir)
    
    # show/verify sizes of datasets
    timit_data.dataset_stats()

    print(f'Script completed in {time.time()-start:.2f} secs')

    return 0

def parse_args():
    parser = argparse.ArgumentParser(description='Timit dataset builder')
    parser.add_argument('--timit_path', type=str, default='../timit/data',
                         help='location of Timit Train and Test directories')
    parser.add_argument('--timit_dict_file', type=str, default='timit_dict.npy',
                         help='location to save phoneme dictionary object')
    parser.add_argument('--phoneme_dict', type=str, default='../timit/TIMITDIC.TXT',
                         help='location of phoneme dictionary')
    parser.add_argument('--out_dir', type=str, default='data', help='location to save datasets')
    parser.add_argument('--num_ffts', type=int, default=60, help='n_fft for feature extraction')
    parser.add_argument('--hop_length', type=int, default=160, help='hop_length for feature extraction')
    parser.add_argument('--num_mels', type=int, default=22, help='number of mels')
    parser.add_argument('--num_mfccs', type=int, default=12, help='number of mfccs')

    return parser.parse_args()

if __name__ == '__main__':
    args = parse_args()
    sys.exit(main(args))
