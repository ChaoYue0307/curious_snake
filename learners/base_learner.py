'''    
    Byron C Wallace
    Tufts Medical Center: Computational and Analytic Evidence Sythensis (tuftscaes.org)
    Curious Snake
    base_learner.py
    --
    This module contains the BaseLearner class, which you can subclass  to implement your own 
    (pool-based) active learning strategy. BaseLearner itself can actually be used directly; it implements
    the 'random' strategy, i.e., it picks examples for the expert to label at random. 
'''

import pdb
import os
import sys
import random
import math
import dataset 
import cluster
import numpy
import smote
path_to_libsvm = os.path.join(os.getcwd(), "libsvm", "python")
sys.path.append(path_to_libsvm)
import svm
from svm import *

class BaseLearner:
    '''
    Base learner class. Sub-class this object to implement your own learning strategy. 
    
    Repeating the comment in curious_snake.py, Curious Snake was originally written for a scenario in which multiple feature spaces
    were being exploited, thus pluralizing may of the attributes in this class. For example, 
    *lists* of unlabeled_datasets and models are kept. If you only have one feature space that you're interested
     in, as is often the case, simply pass around unary lists.  
    ''' 
    
    # TODO add (optional?) schohn/general stopping criterion implementation  -- where should this go?
    
    def __init__(self, unlabeled_datasets = [], models=None):
        '''
        unlabeled_datasets should be either (1) a string pointing to a single data file (e.g., "mydata.txt") or (2) a list of strings
        pointing to multiple data files that represent the same data with different feature spaces. For more on the data format,
        consult the doc or see the samples.
        '''
        # params correspond to each of the respective models (one if we're in a single feature space)
        # these specify things like what kind of kernel to use. here we just use the default, but
        # *you'll probably want to overwrite this* in your subclass. see the libsvm doc for more information (in particular,
        # the svm_test.py is helpful).
        if type(unlabeled_datasets) == type(""):
            # then a string, presumably pointing to a single data file, was passed in
            unlabeled_datasets  = [unlabeled_datasets]
            
        self.params = [svm_parameter()  for d in unlabeled_datasets]
        self.unlabeled_datasets = unlabeled_datasets
        # initialize empty labeled datasets (i.e., all data is unlabeled to begin with)
        self.labeled_datasets = [dataset.dataset([]) for d in unlabeled_datasets]
        self.models = models
        self.div_hash = {}
        self.dist_hash = {}
        self.query_function = self.base_q_function # throws exception if not overridden 
        self.k_hash = {}
        self.name = "Base"
        
        # default prediction function; only important if you're aggregating multiple feature spaces (see 
        # cautious_predict function documentation)
        self.predict = self.majority_predict
 
    
    def base_q_function(self, k):
        ''' overwite this method with query function of choice (e.g., SIMPLE) '''
        raise Exception, "no query function provided!"
 
        
    def active_learn(self, num_examples_to_label, num_to_label_at_each_iteration=5, 
                                                rebuild_models_at_each_iter=True):
        ''''
        Core active learning loop. Uses the provided query function (query_function) to select a number of examples 
        (num_to_label_at_each_iteration) to label at each step, until the total number of examples requested 
        (num_examples_to_label) has been labeled. The models will be updated at each iteration.
        '''
        labeled_so_far = 0
        while labeled_so_far < num_examples_to_label:
            print "labeled %s out of %s" % (labeled_so_far, num_examples_to_label)
            example_ids_to_label = self.query_function(num_to_label_at_each_iteration)
            # now remove the selected examples from the unlabeled sets and put them in the labeled sets.
            # if not ids are returned -- ie., if a void query_function is used --
            # it is assumed the query function took care of labeling the examples selected. 
            if example_ids_to_label:
                self.label_instances_in_all_datasets(example_ids_to_label)
                
            if rebuild_models_at_each_iter:
                self.rebuild_models()
                print "models rebuilt with %s labeled examples" % len(self.labeled_datasets[0].instances)    
            else:
                print "model has %s labeled examples thus far (not rebuilding models @ each iter)" % len(self.labeled_datasets[0].instances)

            labeled_so_far += num_to_label_at_each_iteration
        
        self.rebuild_models()
        print "active learning loop completed; models rebuilt."

                                 
    def label_all_data(self):
        '''
        Labels all the examples in the training set
        '''
        inst_ids = [inst.id for inst in self.unlabeled_datasets[0].instances]
        self.label_instances_in_all_datasets(inst_ids)
        
    def label_instances_in_all_datasets(self, inst_ids):
        '''
        Removes the instances in inst_ids (a list of instance numbers to 'label') from the unlabeled dataset(s) and places
        them in the labeled dataset(s). These will subsequently be used in training models, thus this simulates 'labeling'
        the instances.
        '''
        for unlabeled_dataset, labeled_dataset in zip(self.unlabeled_datasets, self.labeled_datasets):
            labeled_dataset.add_instances(unlabeled_dataset.remove_instances(inst_ids))  
    
    def majority_predict(self, X):
        '''
        If there are multiple models built over different feature spaces, this predicts a label for an instance based on the
        majority vote of these classifiers -- otherwise this is simply "predict"
        '''
        votes = []
        if self.models and len(self.models):
            for m,x in zip(self.models, X):
                votes.append(m.predict(x))
            vote_set = list(set(votes))
            count_in_list = lambda x: votes.count(x)
            return vote_set[_arg_max(vote_set, count_in_list)]
        else:
            raise Exception, "No models have been initialized."
        
        
    def cautious_predict(self, X):
        '''
        A naive way of combining different models (built over different feature-spaces); if any othe models vote yes, then vote yes.
        When there is only on feature space, this reduces to simply "predict".
        '''
        if self.models and len(self.models):
            return max([m.predict(x) for m,x in zip(self.models, X)])
        else:
            raise Exception, "No models have been initialized."
        
    def predict(self, X):
        #
        # overwrite this method if you want to aggregate the predictions over the existing
        # feature spaces differently!
        #
        return self.cautious_predict(X)
        
    
    def pick_balanced_initial_training_set(self, k):
        '''
        Picks k + and k - examples at random for bootstrap set.
        '''
        minority_ids_to_label = self.unlabeled_datasets[0].pick_random_minority_instances(k)
        majority_ids_to_label = self.unlabeled_datasets[0].pick_random_majority_instances(k)
        all_ids_to_label = minority_ids_to_label + majority_ids_to_label
        self.label_instances_in_all_datasets(all_ids_to_label)
        return all_ids_to_label
        
        
    def undersample_labeled_datasets(self, k=None):
        '''
        Undersamples the current labeled datasets, i.e., makes the two classes of equal sizes. 
        Note that this methods returns a *copy* of the undersampled datasets. Thus it
        *does not mutate the labeled datasets*.
        '''
        if self.labeled_datasets and len(self.labeled_datasets) and (len(self.labeled_datasets[0].instances)):
            if not k:
                print "undersampling majority class to equal that of the minority examples"
                # we have to include 'false' minorities -- i.e., instances we've assumed are positives -- because otherwise we'd be cheating
                k = self.labeled_datasets[0].number_of_majority_examples() - self.labeled_datasets[0].number_of_minority_examples()
            # we copy the datasets rather than mutate the class members.
            copied_datasets = [dataset.dataset(list(d.instances)) for d in self.labeled_datasets]
            if k < self.labeled_datasets[0].number_of_majority_examples() and k > 0:
                # make sure we have enough majority examples...
                print "removing %s majority instances. there are %s total majority examples in the dataset." % (k, self.labeled_datasets[0].number_of_majority_examples())
                removed_instances = copied_datasets[0].undersample(k)
                # get the removed instance numbers
                removed_instance_nums = [inst.id for inst in removed_instances]
                # if there is more than one feature-space, remove the same instances from the remaining spaces (sets)
                for labeled_dataset in copied_datasets[1:]:
                    # now remove them from the corresponding sets
                    labeled_dataset.remove_instances(removed_instance_nums)
        else:
            raise Exception, "No labeled data has been provided!"   
        return copied_datasets
    
         
    def get_random_unlabeled_ids(self, k):
        '''
        Returns a random set of k instance ids
        ''' 
        selected_ids = []
        ids = self.unlabeled_datasets[0].get_instance_ids()  
        for i in range(k):
            random_id = random.choice(ids)
            ids.remove(random_id)
            selected_ids.append(random_id)
        return selected_ids
        

    def rebuild_models(self, undersample_first=False):
        '''
        Rebuilds all models over the current labeled datasets.
        '''    
        if undersample_first:
            print "undersampling before building models.."
            datasets = self.undersample_labeled_datasets()
            print "done."
        else:
            datasets = self.labeled_datasets
            
        print "training model(s) on %s instances" % len(datasets[0].instances)
        self.models = []
        for dataset, param in zip(datasets, self.params):
            samples, labels = dataset.get_samples_and_labels()
            problem = svm_problem(labels, samples)
            self.models.append(svm_model(problem, param))
        print "done."         


    def write_out_labeled_data(self, path, dindex=0):
        outf = open(path, 'w')
        outf.write(self.labeled_datasets[dindex].get_points_str())
        outf.close()

    def unlabel_instances(self, inst_ids):
        for inst_index in range(len(self.labeled_datasets[0].instances)):
            if self.labeled_datasets[0].instances[inst_index].id in inst_ids:
                for unlabeled_dataset, labeled_dataset in zip(self.unlabeled_datasets, self.labeled_datasets):
                    labeled_dataset.instances[inst_index].lbl = labeled_dataset.instances[inst_index].label
                    labeled_dataset.instances[inst_index].has_synthetic_label = False

        # now remove the instances and place them into the unlabeled set
        for unlabeled_dataset, labeled_dataset in zip(self.unlabeled_datasets, self.labeled_datasets):
            unlabeled_dataset.add_instances(labeled_dataset.remove_instances(inst_ids))
                
    def _get_dist_from_l(self, model, data, x):
        min_dist = None
        for y in data.instances:
            if not (x.id, y.id) in self.dist_hash:
                self.dist_hash[(x.id, y.id)] = model.compute_dist_between_examples(x.point, y.point)
            if not min_dist or self.dist_hash[(x.id, y.id)] < min_dist:
                min_dist = self.dist_hash[(x.id, y.id)]
        return min_dist
        
    
    def _compute_div(self, model, data, x):
        sum = 0.0
        for y in data.instances:
            # have we already computed this?
            if not (x.id, y.id) in self.div_hash:
                # if not, compute the function and add to the hash
                self.div_hash[(x.id, y.id)] = model.compute_cos_between_examples(x.point, y.point)
            sum+= self.div_hash[(x.id, y.id)]
        return sum
    
    
                      
    def _compute_cos(self, model, x, y):
        if not (x.id, y.id) in self.div_hash:
            self.div_hash[(x.id, y.id)] = model.compute_cos_between_examples(x.point, y.point)
        return self.div_hash[(x.id, y.id)]
    
    
def _arg_max(ls, f):
    ''' Returns the index for x in ls for which f(x) is maximal w.r.t. the rest of the list '''
    return_index = 0
    max_val = f(ls[0])
    for i in range(len(ls)-1):
        if f(ls[i+1]) > max_val:
            return_index = i
            max_val = f(ls[i+1])
    return return_index

        