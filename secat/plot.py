import pandas as pd
import numpy as np
import click
import sqlite3
import os
import sys

try:
    import matplotlib
    matplotlib.use('Agg')
    from matplotlib.backends.backend_pdf import PdfPages
    from matplotlib.lines import Line2D
    import matplotlib.pyplot as plt
except ImportError:
    plt = None

def check_sqlite_table(con, table):
    table_present = False
    c = con.cursor()
    c.execute('SELECT count(name) FROM sqlite_master WHERE type="table" AND name="%s"' % table)
    if c.fetchone()[0] == 1:
        table_present = True
    else:
        table_present = False
    c.fetchall()

    return(table_present)

class plot_features:
    def __init__(self, infile, interaction_id, interaction_qvalue, bait_id, bait_qvalue, peptide_rank):
        self.infile = infile
        self.interaction_id = interaction_id
        self.interaction_qvalue = interaction_qvalue
        self.bait_id = bait_id
        self.bait_qvalue = bait_qvalue
        self.peptide_rank = peptide_rank

        # Read peptide and feature data
        self.feature_data = self.read_features()
        self.peptide_data = self.read_peptides()

        # Read meta data if available
        self.interactions_dmeta = self.read_interactions_dmeta()
        self.interactions_qmeta = self.read_interactions_qmeta()

        self.monomer_qmeta = self.read_monomer_qmeta()


        if self.interaction_id is not None:
            self.plot_interaction(interaction_id)

        if self.bait_id is not None:
            self.plot_bait(bait_id, 0)

        if self.interaction_qvalue is not None:
            interaction_ids, result_ids = self.read_interactions()
            for interaction_id, result_id in zip(interaction_ids, result_ids):
                self.plot_interaction(interaction_id, result_id)

        if self.bait_qvalue is not None:
            bait_ids, result_ids = self.read_baits()
            for bait_id, result_id in zip(bait_ids, result_ids):
                self.plot_bait(bait_id, result_id)

    def plot_interaction(self, interaction_id, result_id):
        feature_data = self.feature_data
        peptide_data = self.peptide_data

        feature_data = feature_data[feature_data['interaction_id'] == interaction_id]
        proteins = pd.DataFrame({"protein_id": pd.concat([feature_data['bait_id'], feature_data['prey_id']])}).drop_duplicates()
        peptide_data = pd.merge(peptide_data, proteins, how='inner', on='protein_id')
        out = os.path.splitext(os.path.basename(self.infile))[0]+"_"+str(result_id).zfill(6)+"_"+interaction_id+".pdf"

        with PdfPages(out) as pdf:
            f = self.generate_plot(peptide_data, feature_data, feature_data['bait_id'].values[0], feature_data['prey_id'].values[0])
            pdf.savefig()
            plt.close()

    def plot_bait(self, bait_id, result_id):
        feature_data = self.feature_data
        peptide_data = self.peptide_data

        interaction_data = self.interactions_dmeta[['bait_id','prey_id','interaction_id']].drop_duplicates()
        interaction_data = interaction_data[(interaction_data['bait_id'] == bait_id) | (interaction_data['prey_id'] == bait_id)]

        # Add monomer
        interaction_data = pd.concat([pd.DataFrame({'bait_id': [bait_id], 'prey_id': [bait_id], 'interaction_id': [bait_id + "_" + bait_id]}), interaction_data], sort=False)

        out = os.path.splitext(os.path.basename(self.infile))[0]+"_"+str(result_id).zfill(6)+"_"+bait_id+".pdf"

        with PdfPages(out) as pdf:
            for idx, interaction in interaction_data.iterrows():
                feature_data_int = feature_data[feature_data['interaction_id'] == interaction['interaction_id']]
                if feature_data_int.shape[0] > 0:
                    proteins_int = pd.DataFrame({"protein_id": pd.concat([feature_data_int['bait_id'], feature_data_int['prey_id']])}).drop_duplicates()
                    peptide_data_int = pd.merge(peptide_data, proteins_int, how='inner', on='protein_id')

                    f = self.generate_plot(peptide_data_int, feature_data_int, feature_data_int['bait_id'].values[0], feature_data_int['prey_id'].values[0])
                    pdf.savefig()
                    plt.close()
                elif interaction['interaction_id'] == (bait_id + "_" + bait_id):
                    f = self.generate_plot(peptide_data[peptide_data['protein_id'] == bait_id], feature_data_int, bait_id, bait_id)
                    pdf.savefig()
                    plt.close()

    def read_features(self):
        con = sqlite3.connect(self.infile)

        df = pd.read_sql('SELECT *, condition_id || "_" || replicate_id AS tag, bait_id || "_" || prey_id AS interaction_id FROM FEATURE_SCORED;', con)

        con.close()

        return df

    def read_peptides(self):
        con = sqlite3.connect(self.infile)

        df = pd.read_sql('SELECT SEC.condition_id || "_" || SEC.replicate_id AS tag, SEC.condition_id, SEC.replicate_id, SEC.sec_id, QUANTIFICATION.protein_id, QUANTIFICATION.peptide_id, peptide_intensity, MONOMER.sec_id AS monomer_sec_id FROM QUANTIFICATION INNER JOIN PROTEIN_META ON QUANTIFICATION.protein_id = PROTEIN_META.protein_id INNER JOIN PEPTIDE_META ON QUANTIFICATION.peptide_id = PEPTIDE_META.peptide_id INNER JOIN SEC ON QUANTIFICATION.RUN_ID = SEC.RUN_ID INNER JOIN MONOMER ON QUANTIFICATION.protein_id = MONOMER.protein_id and SEC.condition_id = MONOMER.condition_id AND SEC.replicate_id = MONOMER.replicate_id WHERE peptide_rank <= %s;' % (self.peptide_rank), con)

        con.close()

        return df

    def read_interactions(self):
        con = sqlite3.connect(self.infile)

        if check_sqlite_table(con, 'EDGE'):
            df = pd.read_sql('SELECT DISTINCT bait_id || "_" || prey_id AS interaction_id FROM EDGE WHERE qvalue < %s ORDER BY pvalue ASC;' % (self.interaction_qvalue), con)
        else:
            df = pd.read_sql('SELECT DISTINCT bait_id || "_" || prey_id AS interaction_id FROM FEATURE_SCORED_COMBINED WHERE pvalue < %s ORDER BY qvalue ASC;' % (self.interaction_qvalue), con)

        con.close()

        return df['interaction_id'].values, df.index+1

    def read_interactions_dmeta(self):
        con = sqlite3.connect(self.infile)

        df = pd.read_sql('SELECT FEATURE_SCORED_COMBINED.bait_id AS bait_id, FEATURE_SCORED_COMBINED.prey_id AS prey_id, FEATURE_SCORED_COMBINED.bait_id || "_" || FEATURE_SCORED_COMBINED.prey_id AS interaction_id, BAIT_META.protein_name AS bait_name, PREY_META.protein_name AS prey_name, (FEATURE_SCORED_COMBINED.pvalue) AS pvalue, min(FEATURE_SCORED_COMBINED.qvalue) AS qvalue FROM FEATURE_SCORED_COMBINED INNER JOIN (SELECT * FROM PROTEIN) AS BAIT_META ON FEATURE_SCORED_COMBINED.bait_id = BAIT_META.protein_id INNER JOIN (SELECT * FROM PROTEIN) AS PREY_META ON FEATURE_SCORED_COMBINED.prey_id = PREY_META.protein_id INNER JOIN (SELECT DISTINCT bait_id, prey_id FROM COMPLEX_QM) AS COMPLEX_QM ON FEATURE_SCORED_COMBINED.bait_id = COMPLEX_QM.bait_id AND FEATURE_SCORED_COMBINED.prey_id = COMPLEX_QM.prey_id GROUP BY FEATURE_SCORED_COMBINED.bait_id, FEATURE_SCORED_COMBINED.prey_id;', con)

        con.close()

        return df

    def read_interactions_qmeta(self):
        con = sqlite3.connect(self.infile)

        df = None

        if check_sqlite_table(con, 'EDGE'):
            df = pd.read_sql('SELECT *, "combined" AS level, bait_id || "_" || prey_id AS interaction_id FROM EDGE UNION SELECT condition_1, condition_2, bait_id, prey_id, pvalue, qvalue, level, bait_id || "_" || prey_id AS interaction_id FROM EDGE_LEVEL;', con)

        con.close()

        return df

    def read_monomer_qmeta(self):
        con = sqlite3.connect(self.infile)

        df = None

        if check_sqlite_table(con, 'NODE'):
            df = pd.read_sql('SELECT *, "combined" AS level FROM NODE UNION SELECT condition_1, condition_2, bait_id, pvalue, qvalue, level FROM NODE_LEVEL;', con)

        con.close()

        return df

    def read_baits(self):
        con = sqlite3.connect(self.infile)

        df = pd.read_sql('SELECT DISTINCT bait_id FROM NODE WHERE qvalue < %s ORDER BY pvalue ASC;' % (self.bait_qvalue), con)

        con.close()

        return df['bait_id'].values, df.index+1

    def generate_plot(self, peptide_data, feature_data, bait_id, prey_id):
        interaction_id = bait_id + "_" + prey_id

        tags = peptide_data.sort_values(by=['tag'])['tag'].drop_duplicates().values.tolist()

        f = plt.figure(figsize=(12,(len(tags)+1)*2.5))

        # Axes that share the x- and y-axes
        ax = f.add_subplot(len(tags)+1, 1, 1)
        axarr = [ax] + [f.add_subplot(len(tags)+1, 1, i, sharex=ax, sharey=ax) for i in range(2, len(tags)+1)]
        # The bottom independent subplot
        axarr.append(f.add_subplot(len(tags)+1, 1, len(tags)+1))

        # plot detection metadata
        if bait_id is not prey_id:
            dmeta = self.interactions_dmeta
            dmeta = dmeta[dmeta['interaction_id'] == interaction_id][['bait_name','prey_name','pvalue','qvalue']]
            titletext = str(interaction_id) + "\n" + str(dmeta['bait_name'].values[0]) + " vs "  + str(dmeta['prey_name'].values[0]) + "\n" + "p-value: "  + str(np.round(dmeta['pvalue'].values[0], 3)) + " q-value: "  + str(np.round(dmeta['qvalue'].values[0], 3))
        else:
            titletext = str(interaction_id)
        f.suptitle(titletext)

        xmin = 0 # peptide_data['sec_id'].min()
        xmax = peptide_data['sec_id'].max()
        ymin = 0 #peptide_data['peptide_intensity'].min()
        ymax = peptide_data['peptide_intensity'].max() * 1.2

        # plot interactions
        for tag in tags:
            axarr[tags.index(tag)].set_xlim(xmin, xmax)
            axarr[tags.index(tag)].set_ylim(ymin, ymax)
            proteins = peptide_data['protein_id'].drop_duplicates().values
            for protein in proteins:
                if protein == bait_id:
                    protein_color = 'red'
                else:
                    protein_color = 'black'
                # plot monomer threshold
                axarr[tags.index(tag)].axvline(x=peptide_data[peptide_data['protein_id'] == protein]['monomer_sec_id'].mean(), color=protein_color, alpha=0.5)

                # plot peptide chromatograms
                peptides = peptide_data[peptide_data['protein_id'] == protein]['peptide_id'].drop_duplicates().values
                for peptide in peptides:
                    points = peptide_data[(peptide_data['peptide_id'] == peptide) & (peptide_data['tag'] == tag)].sort_values(by=['sec_id'])

                    axarr[tags.index(tag)].plot(points['sec_id'], points['peptide_intensity'], color=protein_color)

            # plot legend and subtitle
            if bait_id is not prey_id:
                axarr[tags.index(tag)].legend([Line2D([0], [0], color='red'), Line2D([0], [0], color='black')], [bait_id, prey_id])
            axarr[tags.index(tag)].set_title(tag, loc = 'center', pad = -15)

            # plot feature information if present
            feature = feature_data[(feature_data['bait_id'] == bait_id) & (feature_data['prey_id'] == prey_id) & (feature_data['tag'] == tag)]

            if feature.shape[0] > 0:
                feature_string = "p-value: %s\nq-value: %s\npep: %s" % (np.round(feature['pvalue'].mean(),3),np.round(feature['qvalue'].mean(),3),np.round(feature['pep'].mean(),3))
                axarr[tags.index(tag)].text(0.01, 0.95, feature_string, transform=axarr[tags.index(tag)].transAxes, fontsize=10, verticalalignment='top', bbox=dict(boxstyle='square', facecolor='wheat', alpha=0.5))

        # plot quantitative metadata
        if bait_id == prey_id:
            mmeta = self.monomer_qmeta
            mmeta = mmeta[mmeta['bait_id'] == bait_id][['level','condition_1','condition_2','pvalue','qvalue']].sort_values(by='pvalue')
            if mmeta.shape[0] > 0:
                axarr[len(tags)].table(cellText=mmeta.values, colLabels=mmeta.columns, loc='center')
            axarr[len(tags)].axis('off')
        elif self.interactions_qmeta is not None:
            qmeta = self.interactions_qmeta
            qmeta = qmeta[qmeta['interaction_id'] == interaction_id][['level','condition_1','condition_2','pvalue','qvalue']].sort_values(by='pvalue')
            if qmeta.shape[0] > 0:
                axarr[len(tags)].table(cellText=qmeta.values, colLabels=qmeta.columns, loc='center')
            axarr[len(tags)].axis('off')

        return f

