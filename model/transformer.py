import numpy as np
import torch
import torch.nn as nn

from model.encoder import Encoder
from model.decoder import Decoder


class Transformer(nn.Module):
    def __init__(self, params):
        super(Transformer, self).__init__()
        self.params = params
        self.hidden_dim = params.hidden_dim

        self.device = params.device
        self.encoder = Encoder(params)
        self.decoder = Decoder(params)

    def create_subsequent_mask(self, target):
        # target = [batch size, target length]

        batch_size, target_length = target.size()

        # torch.triu returns the upper triangular part of a matrix based on user defined diagonal
        '''
        if target length is 5 and diagonal is 1, this function returns
            [[0, 1, 1, 1, 1],
             [0, 0, 1, 1, 1],
             [0, 0, 0, 1, 1],
             [0, 0, 0, 0, 1],
             [0, 0, 0, 0, 1]]
        '''
        subsequent_mask = torch.triu(torch.ones(target_length, target_length), diagonal=1).bool().to(self.device)
        # subsequent_mask = [target length, target length]

        # clone subsequent mask 'batch size' times to cover all data instances in the batch
        subsequent_mask = subsequent_mask.unsqueeze(0).repeat(batch_size, 1, 1)
        # subsequent_mask = [batch size, target length, target length]

        return subsequent_mask

    def create_mask(self, source, target, subsequent_mask):
        # source          = [batch size, source length]
        # target          = [batch size, target length]
        # subsequent_mask = [batch size, target length, target length]
        source_length = source.shape[1]
        target_length = target.shape[1]

        # create boolean tensors which will be used to mask padding tokens of both source and target sentence
        source_mask = (source == self.params.pad_idx)
        target_mask = (target == self.params.pad_idx)
        # source mask    = [batch size, source length]
        # target mask    = [batch size, target length]

        # repeat source sentence masking tensor 'target sentence length' times: dec_enc_mask
        dec_enc_mask = source_mask.unsqueeze(1).repeat(1, target_length, 1)
        # repeat source sentence masking tensor 'source sentence length' times: source_mask
        source_mask = source_mask.unsqueeze(1).repeat(1, source_length, 1)
        # repeat target sentence masking tensor 'target sentence length' times: target_mask
        target_mask = target_mask.unsqueeze(1).repeat(1, target_length, 1)

        # dec enc mask   = [batch size, target length, source length]
        # source mask    = [batch size, source length, source length]
        # target mask    = [batch size, target length, target length]

        # combine pad token masking tensor and subsequent masking tensor for decoder's self attention
        target_mask = target_mask | subsequent_mask
        # target mask = [batch size, target length, target length]

        return source_mask, target_mask, dec_enc_mask

    def create_positional_encoding(self, batch_size, sentence_len):
        # PE(pos, 2i)     = sin(pos/10000 ** (2*i / hidden_dim)
        # PE(pos, 2i + 1) = cos(pos/10000 ** (2*i / hidden_dim)
        sinusoid_table = np.array([pos/np.power(10000, 2*i/self.hidden_dim)
                                   for pos in range(sentence_len) for i in range(self.hidden_dim)])
        # sinusoid table = [sentence length * hidden dim]

        sinusoid_table = sinusoid_table.reshape(sentence_len, -1)
        # sinusoid table = [sentence length, hidden dim]

        # calculate positional encoding for even numbers
        sinusoid_table[0::2, :] = np.sin(sinusoid_table[0::2, :])
        # calculate positional encoding for odd numbers
        sinusoid_table[1::2, :] = np.sin(sinusoid_table[1::2, :])

        # convert numpy based sinusoid to torch.tensor and repeat it 'batch size' times
        sinusoid_table = torch.FloatTensor(sinusoid_table).to(self.device)
        sinusoid_table = sinusoid_table.unsqueeze(0).repeat(batch_size, 1, 1)
        # sinusoid table = [batch size, sentence length, hidden dim]

        return sinusoid_table

    def forward(self, source, target):
        # source = [batch size, source length]
        # target = [batch size, target length]
        source_batch, source_len = source.size()
        target_batch, target_len = target.size()

        # create masking tensor for self attention (encoder & decoder) and decoder's attention on the output of encoder
        subsequent_mask = self.create_subsequent_mask(target)
        source_mask, target_mask, dec_enc_mask = self.create_mask(source, target, subsequent_mask)

        source_positional_encoding = self.create_positional_encoding(source_batch, source_len)
        target_positional_encoding = self.create_positional_encoding(target_batch, target_len)

        source = self.encoder(source, source_mask, source_positional_encoding)
        output = self.decoder(target, source, target_mask, dec_enc_mask, target_positional_encoding)
        # output = [batch size, target length, output dim]

        return output

    def count_parameters(self):
        return sum(p.numel() for p in self.parameters() if p.requires_grad)
