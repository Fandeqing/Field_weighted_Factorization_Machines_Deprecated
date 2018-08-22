import time 
import sys
from sklearn.metrics import roc_auc_score
import numpy as np
from time import gmtime, strftime
import configparser
from conf.conf_fwfm3 import *
from conf.conf_fwfm import *
from conf.conf_MTLfwfm import *
from conf.conf_ffm import *
from conf.conf_lr import *
from conf.conf_fm import *
from conf.conf_DINN import *

import utils
from models import LR, FM, PNN1, PNN1_Fixed, PNN2, FNN, CCPM, Fast_CTR, Fast_CTR_Concat, FwFM, FwFM3, FFM, FwFM_LE, MultiTask_FwFM, DINN

config = configparser.ConfigParser()
config.read(sys.argv[1])
path_train = config['setup']['path_train']
path_validation = config['setup']['path_validation']
path_test = config['setup']['path_test']
path_feature_index = config['setup']['path_feature_index']

print "path_train: ", path_train
print "path_validation: ", path_validation
print "path_test: ", path_test
sys.stdout.flush()

INPUT_DIM, FIELD_OFFSETS, FIELD_SIZES = utils.initiate(path_feature_index)

print 'FIELD_SIZES', FIELD_SIZES

train_label = utils.read_label(path_train)
validation_label = utils.read_label(path_validation)
test_label = utils.read_label(path_test)

train_size = train_label.shape[0]
validation_size = validation_label.shape[0]
test_size = test_label.shape[0]
num_feas = len(utils.FIELD_SIZES)

min_round = 1
num_round = 1000
early_stop_round = 2
batch_size = 1000
#bb = 10
round_no_improve = 5

field_offsets = utils.FIELD_OFFSETS

def train(model, name, in_memory = True, flag_MTL = True):
    #builder = tf.saved_model.builder.SavedModelBuilder('model')
    global batch_size, time_run, time_read, time_process
    history_score = []
    best_score = -1
    best_epoch = -1
    start_time = time.time()
    print 'epochs\tloss\ttrain-auc\teval-auc\ttime'
    sys.stdout.flush()
    if in_memory:
        train_data = utils.read_data(path_train, INPUT_DIM)
        validation_data = utils.read_data(path_validation, INPUT_DIM)
        test_data = utils.read_data(path_test, INPUT_DIM)
        model_name = name.split('_')[0]
        if model_name in set(['lr', 'fm']):
            train_data_tmp = utils.split_data(train_data, FIELD_OFFSETS)
            validation_data_tmp = utils.split_data(validation_data, FIELD_OFFSETS)
            test_data_tmp = utils.split_data(test_data, FIELD_OFFSETS)
        else:
            train_data = utils.split_data(train_data, FIELD_OFFSETS)
            validation_data = utils.split_data(validation_data, FIELD_OFFSETS)
            test_data = utils.split_data(test_data, FIELD_OFFSETS)
    for i in range(num_round):
        fetches = [model.optimizer, model.loss]
        if batch_size > 0:
            ls = []
            if in_memory:
                for j in range(train_size / batch_size + 1):
                    X_i, y_i = utils.slice(train_data, j * batch_size, batch_size)
                    _, l = model.run(fetches, X_i, y_i)
                    ls.append(l)
            else:
                f = open(path_train, 'r')
                lst_lines = []
                for line in f:
                    if len(lst_lines) < batch_size:
                        lst_lines.append(line)
                    else:
                        X_i, y_i = utils.slice(utils.process_lines(lst_lines, name, INPUT_DIM, FIELD_OFFSETS), 0, -1) # type of X_i, X_i[0], X_i[0][0] is list, tuple and np.ndarray respectively.
                        _, l = model.run(fetches, X_i, y_i)
                        ls.append(l)
                        lst_lines = [line]
                f.close()
                if len(lst_lines) > 0:
                    X_i, y_i = utils.slice(utils.process_lines(lst_lines, name, INPUT_DIM, FIELD_OFFSETS), 0, -1)
                    _, l = model.run(fetches, X_i, y_i)
                    ls.append(l)
        elif batch_size == -1:
            pass
        model.dump('model/' + name + '_epoch_' + str(i))
        if in_memory:
            lst_train_preds = []
            lst_validation_preds = []
            lst_test_preds = []
            for j in range(train_size / batch_size + 1):
                X_i, y_i = utils.slice(train_data, j * batch_size, batch_size)
                p = model.run(model.y_prob, X_i, y_i)
                lst_train_preds.append(p)
            for j in range(validation_size / batch_size + 1):
                X_i, y_i = utils.slice(validation_data, j * batch_size, batch_size)
                p = model.run(model.y_prob, X_i, y_i)
                lst_validation_preds.append(p)
            for j in range(test_size / batch_size + 1):
                X_i, y_i = utils.slice(test_data, j * batch_size, batch_size)
                p = model.run(model.y_prob, X_i, y_i)
                lst_test_preds.append(p)
            train_preds = np.concatenate(lst_train_preds)
            validation_preds = np.concatenate(lst_validation_preds)
            test_preds = np.concatenate(lst_test_preds)
            train_score = roc_auc_score(train_data[1], train_preds)
            validation_score = roc_auc_score(validation_data[1], validation_preds)
            test_score = roc_auc_score(test_data[1], test_preds)
            train_score_sum = 0
            train_score_weight = 0
            validation_score_sum = 0
            validation_score_weight = 0
            test_score_sum = 0
            test_score_weight = 0
            print '%d\t%f\t%f\t%f\t%f\t%f\t%s' % (i, np.mean(ls), train_score, validation_score, test_score, time.time() - start_time, strftime("%Y-%m-%d %H:%M:%S", gmtime()))
            if flag_MTL:
                d_index_task_label_pred_train = {}
                d_index_task_label_pred_validation = {}
                d_index_task_label_pred_test = {}
                if model_name in set(['lr', 'fm']):
                    index_task_train = train_data_tmp[0][-1].indices
                    index_task_validation = validation_data_tmp[0][-1].indices
                    index_task_test = test_data_tmp[0][-1].indices
                else:
                    index_task_train = train_data[0][-1].indices
                    index_task_validation = validation_data[0][-1].indices
                    index_task_test = test_data[0][-1].indices
                for index_tmp in range(len(index_task_train)):
                    index_task = index_task_train[index_tmp]
                    d_index_task_label_pred_train.setdefault(index_task, [[],[]])
                    d_index_task_label_pred_train[index_task][0].append(train_data[1][index_tmp])
                    d_index_task_label_pred_train[index_task][1].append(train_preds[index_tmp])
                for index_task in sorted(list(set(index_task_train))):
                    auc = roc_auc_score(d_index_task_label_pred_train[index_task][0], d_index_task_label_pred_train[index_task][1])
                    num_samples = len(d_index_task_label_pred_train[index_task][0])
                    train_score_sum += auc * num_samples
                    train_score_weight += num_samples
                    print 'train, index_type: %d, number of samples: %d, AUC: %f' % (index_task, len(d_index_task_label_pred_train[index_task][0]), auc)
                for index_tmp in range(len(index_task_validation)):
                    index_task = index_task_validation[index_tmp]
                    d_index_task_label_pred_validation.setdefault(index_task, [[],[]])
                    d_index_task_label_pred_validation[index_task][0].append(validation_data[1][index_tmp])
                    d_index_task_label_pred_validation[index_task][1].append(validation_preds[index_tmp])
                for index_task in sorted(list(set(index_task_validation))):
                    auc = roc_auc_score(d_index_task_label_pred_validation[index_task][0], d_index_task_label_pred_validation[index_task][1])
                    num_samples = len(d_index_task_label_pred_validation[index_task][0])
                    validation_score_sum += auc * num_samples
                    validation_score_weight += num_samples
                    print 'validation, index_type: %d, number of samples: %d, AUC: %f' % (index_task, num_samples, auc)
                for index_tmp in range(len(index_task_test)):
                    index_task = index_task_test[index_tmp]
                    d_index_task_label_pred_test.setdefault(index_task, [[],[]])
                    d_index_task_label_pred_test[index_task][0].append(test_data[1][index_tmp])
                    d_index_task_label_pred_test[index_task][1].append(test_preds[index_tmp])
                for index_task in sorted(list(set(index_task_test))):
                    auc = roc_auc_score(d_index_task_label_pred_test[index_task][0], d_index_task_label_pred_test[index_task][1])
                    num_samples = len(d_index_task_label_pred_test[index_task][0])
                    test_score_sum += auc * num_samples
                    test_score_weight += num_samples
                    print 'test, index_type: %d, number of samples: %d, AUC: %f' % (index_task, len(d_index_task_label_pred_test[index_task][0]), auc)
            weighted_train_score = train_score_sum / train_score_weight
            print 'weighted_train_score', weighted_train_score
            weighted_validation_score = validation_score_sum / validation_score_weight
            print 'weighted_validation_score', weighted_validation_score
            weighted_test_score = test_score_sum / test_score_weight
            print 'weighted_test_score', weighted_test_score
            history_score.append(weighted_validation_score)
            if weighted_validation_score < best_score and (i - best_epoch) >= 3:
                break
            if weighted_validation_score > best_score:
                best_score = weighted_validation_score
                best_epoch = i
            sys.stdout.flush()
        else:
            lst_train_pred = []
            lst_test_pred = []
            if batch_size > 0:
                f = open(path_train, 'r')
                lst_lines = []
                for line in f:
                    if len(lst_lines) < batch_size:
                        lst_lines.append(line)
                    else:
                        X_i, y_i = utils.slice(utils.process_lines(lst_lines, name, INPUT_DIM, FIELD_OFFSETS), 0, -1)
                        _train_preds = model.run(model.y_prob, X_i)
                        lst_train_pred.append(_train_preds)
                        lst_lines = [line]
                f.close()
                if len(lst_lines) > 0:
                    X_i, y_i = utils.slice(utils.process_lines(lst_lines, name, INPUT_DIM, FIELD_OFFSETS), 0, -1)
                    _train_preds = model.run(model.y_prob, X_i)
                    lst_train_pred.append(_train_preds)
                f = open(path_test, 'r')
                lst_lines = []
                for line in f:
                    if len(lst_lines) < batch_size:
                        lst_lines.append(line)
                    else:
                        X_i, y_i = utils.slice(utils.process_lines(lst_lines, name, INPUT_DIM, FIELD_OFFSETS), 0, -1)
                        _test_preds = model.run(model.y_prob, X_i)
                        lst_test_pred.append(_test_preds)
                        lst_lines = [line]
                f.close()
                if len(lst_lines) > 0:
                    X_i, y_i = utils.slice(utils.process_lines(lst_lines, name, INPUT_DIM, FIELD_OFFSETS), 0, -1)
                    _test_preds = model.run(model.y_prob, X_i)
                    lst_test_pred.append(_test_preds)
            train_preds = np.concatenate(lst_train_pred)
            test_preds = np.concatenate(lst_test_pred)
            print 'np.shape(train_preds)', np.shape(train_preds)
            train_score = roc_auc_score(train_label, train_preds)
            test_score = roc_auc_score(test_label, test_preds)
            print '%d\t%f\t%f\t%f\t%f\t%s' % (i, np.mean(ls), train_score, test_score, time.time() - start_time, strftime("%Y-%m-%d %H:%M:%S", gmtime()))
            sys.stdout.flush()
        '''
        if i == 0:
            map = {}
            for i in range(15):
                map["field_" + str(i) + "_indices"] = model.X[i].indices
                map["field_" + str(i) + "_values"] = model.X[i].values
                map["field_" + str(i) + "_dense_shape"] = model.X[i].dense_shape
            print "save!"
            print model.y_prob.name
            builder.add_meta_graph_and_variables(
                model.sess, 
                [tf.saved_model.tag_constants.SERVING],
                signature_def_map = {
                    "model": tf.saved_model.signature_def_utils.predict_signature_def(
                        inputs = map,
                        outputs = {"y": model.y_prob})
                    })
            builder.save()
        if i == 12:
            break
        '''

def mapConf2Model(name):
    conf = d_name_conf[name]
    model_name = name.split('_')[0]
    #if model_name != 'lr' and model_name != 'fm' and model_name != 'DINN':
    #    conf['layer_sizes'] = [FIELD_SIZES, 10, 1]
    if model_name in set(['lr', 'fm']):
        conf['input_dim'] = INPUT_DIM
    print 'conf', conf
    if model_name == 'ffm':
        return FFM(**conf)
    elif model_name == 'fwfm':
        return FwFM(**conf)
    elif model_name == 'fwfm3':
        return FwFM3(**conf)
    elif model_name == 'fm':
        return FM(**conf)
    elif model_name == 'lr':
        return LR(**conf)
    elif model_name == 'fwfmoh':
        return FwFM_LE(**conf)
    elif model_name == 'MTLfwfm':
        conf['index_lines'] = utils.index_lines
        conf['num_lines'] = FIELD_SIZES[utils.index_lines]
        return MultiTask_FwFM(**conf)
    elif model_name == 'DINN':
        return DINN(**conf)

for name in ['fwfm_l2_v_1e-5_lr_5e-5']:
    print 'name with none activation', name
    sys.stdout.flush()
    model = mapConf2Model(name)
    train(model, name + '_yahoo_dataset2.2', in_memory=True, flag_MTL=True)

    #train(model, name + '_criteo')
