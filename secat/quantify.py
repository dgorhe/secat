import pandas as pd
import numpy as np
import click
import sqlite3
import os
import sys

from EmpiricalBrownsMethod import EmpiricalBrownsMethod
import itertools

from scipy.stats import mannwhitneyu, ttest_ind

from pyprophet.stats import pi0est, qvalue

class quantitative_matrix:
    def __init__(self, outfile):
        self.outfile = outfile

        self.complex, self.monomer = self.read()

    def read(self):
        con = sqlite3.connect(self.outfile)

        monomer_data = pd.read_sql('SELECT feature_meta.condition_id, feature_meta.replicate_id, feature.feature_id, feature.bait_id, feature.prey_id, feature.prey_peptide_id, feature.prey_peptide_intensity, feature.prey_peptide_total_intensity FROM FEATURE INNER JOIN FEATURE_META ON FEATURE.FEATURE_ID = FEATURE_META.FEATURE_ID INNER JOIN FEATURE_MW ON FEATURE.FEATURE_ID = FEATURE_MW.FEATURE_ID AND FEATURE.PREY_ID = FEATURE_MW.PREY_ID INNER JOIN FEATURE_SCORED ON FEATURE.FEATURE_ID = FEATURE_SCORED.FEATURE_ID AND FEATURE.PREY_ID = FEATURE_SCORED.PREY_ID WHERE FEATURE_MW.monomer == 1 AND feature.bait_id == feature.prey_id AND FEATURE.decoy == 0;' , con)
        monomer_data['interaction_id'] = monomer_data.apply(lambda x: "_".join(sorted([x['bait_id'], x['prey_id']])), axis=1)


        complex_data = pd.read_sql('SELECT feature_meta.condition_id, feature_meta.replicate_id, feature.feature_id, feature.bait_id, feature.prey_id, feature.prey_peptide_id, feature.prey_peptide_intensity, feature.prey_peptide_total_intensity FROM FEATURE INNER JOIN FEATURE_META ON FEATURE.FEATURE_ID = FEATURE_META.FEATURE_ID INNER JOIN FEATURE_MW ON FEATURE.FEATURE_ID = FEATURE_MW.FEATURE_ID AND FEATURE.PREY_ID = FEATURE_MW.PREY_ID INNER JOIN FEATURE_SCORED ON FEATURE.FEATURE_ID = FEATURE_SCORED.FEATURE_ID AND FEATURE.PREY_ID = FEATURE_SCORED.PREY_ID WHERE FEATURE_MW.complex == 1 AND FEATURE.decoy == 0;' , con)
        complex_data['interaction_id'] = complex_data.apply(lambda x: "_".join(sorted([x['bait_id'], x['prey_id']])), axis=1)


        con.close()

        ## Monomer
        # Summarize individual features for monomers
        monomer_data = monomer_data.groupby(['condition_id','replicate_id','interaction_id','bait_id','prey_id','prey_peptide_id']).apply(lambda x: pd.Series({'prey_peptide_intensity': np.sum(x['prey_peptide_intensity']), 'prey_peptide_total_intensity': np.mean(x['prey_peptide_total_intensity'])})).reset_index(level=['condition_id','replicate_id','interaction_id','bait_id','prey_id', 'prey_peptide_id'])
        monomer_data['prey_peptide_intensity_fraction'] = monomer_data['prey_peptide_intensity'] / monomer_data['prey_peptide_total_intensity']

        # Summarize peptides
        monomer_data = monomer_data.groupby(['condition_id','replicate_id','interaction_id','bait_id','prey_id']).apply(lambda x: pd.Series({'prey_intensity': np.log(np.median(x['prey_peptide_intensity'])), 'prey_intensity_fraction': np.median(x['prey_peptide_intensity_fraction'])})).reset_index(level=['condition_id','replicate_id','interaction_id','bait_id','prey_id'])

        ## Prey
        # Summarize individual features for preys
        prey_complex_data = complex_data[complex_data['bait_id'] != complex_data['prey_id']].groupby(['condition_id','replicate_id','interaction_id','bait_id','prey_id','prey_peptide_id']).apply(lambda x: pd.Series({'prey_peptide_intensity': np.sum(x['prey_peptide_intensity']), 'prey_peptide_total_intensity': np.mean(x['prey_peptide_total_intensity'])})).reset_index(level=['condition_id','replicate_id','interaction_id','bait_id','prey_id', 'prey_peptide_id'])
        prey_complex_data['prey_peptide_intensity_fraction'] = prey_complex_data['prey_peptide_intensity'] / prey_complex_data['prey_peptide_total_intensity']

        # Summarize peptides
        prey_complex_data = prey_complex_data.groupby(['condition_id','replicate_id','interaction_id','bait_id','prey_id']).apply(lambda x: pd.Series({'prey_intensity': np.log(np.median(x['prey_peptide_intensity'])), 'prey_intensity_fraction': np.median(x['prey_peptide_intensity_fraction'])})).reset_index(level=['condition_id','replicate_id','interaction_id','bait_id','prey_id'])

        ## Bait
        # Prepare individual features for baits and keep relationship to preys
        bait_complex_data = complex_data[complex_data['bait_id'] == complex_data['prey_id']].drop(['prey_id','interaction_id'], axis=1)
        bait_prey_association = complex_data[complex_data['bait_id'] != complex_data['prey_id']][['feature_id','prey_id']].drop_duplicates()
        bait_complex_data = pd.merge(bait_complex_data, bait_prey_association, on='feature_id')

        # Summarize individual features for baits and keep relationship to preys
        bait_complex_data = bait_complex_data.groupby(['condition_id','replicate_id','bait_id','prey_id','prey_peptide_id']).apply(lambda x: pd.Series({'prey_peptide_intensity': np.sum(x['prey_peptide_intensity']), 'prey_peptide_total_intensity': np.mean(x['prey_peptide_total_intensity'])})).reset_index(level=['condition_id','replicate_id','bait_id','prey_id', 'prey_peptide_id'])
        bait_complex_data['prey_peptide_intensity_fraction'] = bait_complex_data['prey_peptide_intensity'] / bait_complex_data['prey_peptide_total_intensity']

        # Summarize peptides
        bait_complex_data = bait_complex_data.groupby(['condition_id','replicate_id','bait_id','prey_id']).apply(lambda x: pd.Series({'bait_intensity': np.log(np.median(x['prey_peptide_intensity'])), 'bait_intensity_fraction': np.median(x['prey_peptide_intensity_fraction'])})).reset_index(level=['condition_id','replicate_id','bait_id','prey_id'])

        ## Bait-Prey
        # Merge bait and prey complex_data
        merged_complex_data = pd.merge(bait_complex_data, prey_complex_data, on=['condition_id','replicate_id','bait_id','prey_id'])
        merged_complex_data['intensity_fraction'] = merged_complex_data['prey_intensity'] / merged_complex_data['bait_intensity']
        merged_complex_data['relative_intensity_fraction'] = merged_complex_data['prey_intensity_fraction'] / merged_complex_data['bait_intensity_fraction']

        return merged_complex_data, monomer_data

class quantitative_test:
    def __init__(self, outfile):
        self.outfile = outfile
        self.levels = ['prey_intensity','prey_intensity_fraction','intensity_fraction','relative_intensity_fraction']
        self.comparisons = self.contrast()

        self.complex, self.monomer = self.read()

        self.edge_directional = self.compare()
        self.edge_level, self.edge, self.node_level, self.node = self.integrate()

    def contrast(self):
        con = sqlite3.connect(self.outfile)
        conditions = pd.read_sql('SELECT DISTINCT condition_id FROM SEC;' , con)['condition_id'].values.tolist()
        con.close()

        comparisons = []
        # prepare single-sample comparisons
        if 'control' in conditions:
            conditions.remove('control')
            for condition in conditions:
                comparisons.append([condition, 'control'])
        # prepare multi-sample comparisons
        else:
            comparisons = list(itertools.combinations(conditions, 2))

        return comparisons

    def read(self):
        con = sqlite3.connect(self.outfile)

        complex_data = pd.read_sql('SELECT COMPLEX_QM.* FROM COMPLEX_QM INNER JOIN (SELECT interaction_id, min(q_value) AS q_value FROM FEATURE_INTERACTION GROUP BY interaction_id) AS FEATURE_INTERACTION ON COMPLEX_QM.interaction_id = FEATURE_INTERACTION.interaction_id WHERE q_value < 0.05;' , con)

        monomer_data = pd.read_sql('SELECT * FROM monomer_qm;' , con)

        con.close()

        return complex_data, monomer_data

    def compare(self):
        dfs = []
        for level in self.levels:
            for comparison in self.comparisons:
                for state in [self.complex, self.monomer]:
                    if level in state.columns:
                        df = self.test(state, level, comparison[0], comparison[1])

                        # Multiple testing correction via q-value
                        df['qvalue'] = qvalue(df['pvalue'].values, pi0est(df['pvalue'].values)['pi0'])
                        dfs.append(df)

        return pd.concat(dfs).sort_values(by='pvalue', ascending=True, na_position='last')

    def test(self, df, level, condition_1, condition_2):
        def stat(x, experimental_design):
            x.set_index('condition_id')
            if condition_1 in x['condition_id'].values and condition_2 in x['condition_id'].values:
                if x['condition_id'].value_counts()[condition_1] > 0 and x['condition_id'].value_counts()[condition_2] > 0:
                    qm = pd.merge(experimental_design, x, how='left')

                    if level == 'score':
                        qm[level].fillna(0, inplace=True)

                    qmt = qm.transpose()
                    qmt.columns = "quantitative" + "_" + experimental_design["condition_id"] + "_" + experimental_design["replicate_id"]
                    # qmt['pvalue'] = mannwhitneyu(qm[qm['condition_id'] == condition_1][level].values, qm[qm['condition_id'] == condition_2][level].values)[1]
                    qmt['pvalue'] = ttest_ind(qm[qm['condition_id'] == condition_1][level].dropna().values, qm[qm['condition_id'] == condition_2][level].dropna().values, equal_var=False)[1]


                    return qmt.loc[level]

        # compute number of replicates
        experimental_design = df[['condition_id','replicate_id']].drop_duplicates()

        df_test = df.groupby(['bait_id','prey_id','interaction_id']).apply(lambda x: stat(x, experimental_design)).reset_index()#.dropna()
        df_test['condition_1'] = condition_1
        df_test['condition_2'] = condition_2
        df_test['level'] = level

        return df_test[['condition_1','condition_2','level','bait_id','prey_id','interaction_id']+[c for c in df_test.columns if c.startswith("quantitative_")]+['pvalue']]

    def integrate(self):
        def collapse(x):
            if x.shape[0] > 1:
                return pd.Series({'pvalue': EmpiricalBrownsMethod(x[[c for c in x.columns if c.startswith("quantitative_")]].values, x['pvalue'].values)})
            elif x.shape[0] == 1:
                return pd.Series({'pvalue': x['pvalue'].values[0]})

        df = self.edge_directional

        df_edge_level = df.groupby(['condition_1', 'condition_2','interaction_id','level']).apply(collapse).reset_index()
        df_edge = df.groupby(['condition_1', 'condition_2','interaction_id']).apply(collapse).reset_index()

        df_node_level = df.groupby(['condition_1', 'condition_2','level','bait_id']).apply(collapse).reset_index()
        df_node = df.groupby(['condition_1', 'condition_2','bait_id']).apply(collapse).reset_index()

        # Multiple testing correction via q-value
        df_edge_level['qvalue'] = qvalue(df_edge_level['pvalue'].values, pi0est(df_edge_level['pvalue'].values)['pi0'])
        df_edge['qvalue'] = qvalue(df_edge['pvalue'].values, pi0est(df_edge['pvalue'].values)['pi0'])

        df_node_level['qvalue'] = qvalue(df_node_level['pvalue'].values, pi0est(df_node_level['pvalue'].values)['pi0'])
        df_node['qvalue'] = qvalue(df_node['pvalue'].values, pi0est(df_node['pvalue'].values)['pi0'])

        return df_edge_level, df_edge, df_node_level, df_node
