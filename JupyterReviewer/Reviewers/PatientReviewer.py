import pandas as pd
import numpy as np
import functools
import time
import os
import re

import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from jupyter_dash import JupyterDash
from dash import dcc
from dash import html
from dash.dependencies import Input, Output, State
from dash.exceptions import PreventUpdate
from dash import Dash, dash_table
import dash
import dash_bootstrap_components as dbc
import functools

from JupyterReviewer.ReviewData import ReviewData, ReviewDataAnnotation
from JupyterReviewer.ReviewDataApp import ReviewDataApp, AppComponent
from JupyterReviewer.ReviewerTemplate import ReviewerTemplate
#from JupyterReviewer.lib.plot_cnp import plot_acr_interactive

def validate_purity(x):
    return (x >= 0) and (x <= 1)

def validate_ploidy(x):
    return x >= 0

def gen_clinical_data_table(df, idx, cols):
    r=df.loc[idx]
    return [dbc.Table.from_dataframe(r[cols].to_frame().reset_index())]

start_pos = 'Start_position' or 'Start_Position'
end_pos = 'End_position' or 'End_Position'
protein_change = 'Protein_change' or 'Protein_Change'
t_ref_count = 't_ref_count' or 't_ref_count_pre_forecall'
t_alt_count = 't_alt_count' or 't_alt_count_pre_forecall'
default_maf_cols = [
    'Hugo_Symbol',
    'Chromosome',
    start_pos,
    end_pos,
    protein_change,
    'Variant_Classification',
    t_ref_count,
    t_alt_count,
    'n_ref_count',
    'n_alt_count'
]
maf_cols_options = []
maf_cols_value = []
hugo_symbols = []
variant_classifications = []
cluster_assignments = [1, 2, 3, 4, 5, 6, 7, 8, 9]

cluster_assignment_colors_dict = {
    1: 'OliveDrab',
    2: 'LightSkyBlue',
    3: 'GoldenRod',
    4: 'DimGray',
    5: 'MediumSlateBlue',
    6: 'Maroon',
    7: 'MediumAquaMarine',
    8: 'LightPink',
    9: 'RebeccaPurple'
}

def get_hex_string(c):
    return '#{:02X}{:02X}{:02X}'.format(*c)

def cluster_color(v):
    phylogic_color_list = [[166, 17, 129],
                           [39, 140, 24],
                           [103, 200, 243],
                           [248, 139, 16],
                           [16, 49, 41],
                           [93, 119, 254],
                           [152, 22, 26],
                           [104, 236, 172],
                           [249, 142, 135],
                           [55, 18, 48],
                           [83, 82, 22],
                           [247, 36, 36],
                           [0, 79, 114],
                           [243, 65, 132],
                           [60, 185, 179],
                           [185, 177, 243],
                           [139, 34, 67],
                           [178, 41, 186],
                           [58, 146, 231],
                           [130, 159, 21],
                           [161, 91, 243],
                           [131, 61, 17],
                           [248, 75, 81],
                           [32, 75, 32],
                           [45, 109, 116],
                           [255, 169, 199],
                           [55, 179, 113],
                           [34, 42, 3],
                           [56, 121, 166],
                           [172, 60, 15],
                           [115, 76, 204],
                           [21, 61, 73],
                           [67, 21, 74],  # Additional colors, uglier and bad
                           [123, 88, 112],
                           [87, 106, 46],
                           [37, 66, 58],
                           [132, 79, 62],
                           [71, 58, 32],
                           [59, 104, 114],
                           [46, 107, 90],
                           [84, 68, 73],
                           [90, 97, 124],
                           [121, 66, 76],
                           [104, 93, 48],
                           [49, 67, 82],
                           [71, 95, 65],
                           [127, 85, 44],  # even more additional colors, gray
                           [88, 79, 92],
                           [220, 212, 194],
                           [35, 34, 36],
                           [200, 220, 224],
                           [73, 81, 69],
                           [224, 199, 206],
                           [120, 127, 113],
                           [142, 148, 166],
                           [153, 167, 156],
                           [162, 139, 145],
                           [0, 0, 0]]  # black
    colors_dict = {str(i): get_hex_string(c) for i, c in enumerate(phylogic_color_list)}

    return colors_dict[str(v)]

def style_data_format(column_id, filter_query, color='Black', backgroundColor='White'):
    return {
        'if': {
            'column_id': column_id,
            'filter_query': '{%s} = "%s"' % (column_id, filter_query)
        },
        'color': color,
        'backgroundColor': backgroundColor,
        'fontWeight': 'bold'
    }

def gen_style_data_conditional(custom_colors):
    style_data_conditional = []

    if 'Cluster_Assignment' in maf_cols_value:
        for n in range(1, 10):
            style_data_conditional.append(style_data_format('Cluster_Assignment', n, color=cluster_assignment_colors_dict[n]))

    if 'functional_effect' in maf_cols_value:
        style_data_conditional.extend([
            style_data_format('functional_effect', 'Likely Loss-of-function', backgroundColor='DarkOliveGreen'),
            style_data_format('functional_effect', 'Likely Gain-of-function', backgroundColor='DarkSeaGreen')
        ])

    if 'oncogenic' in maf_cols_value:
        style_data_conditional.append(style_data_format('oncogenic', 'Likely Oncogenic', backgroundColor='DarkOliveGreen'))

    if 'dbNSFP_Polyphen2_HDIV_ann' in maf_cols_value:
        style_data_conditional.append(style_data_format('dbNSFP_Polyphen2_HDIV_ann', 'D', backgroundColor='FireBrick'))

    if custom_colors != []:
        for list in custom_colors:
            style_data_conditional.append(style_data_format(list[0], list[1], list[2], list[3]))

    return style_data_conditional

def gen_maf_columns(df, idx, cols, hugo, variant, cluster):
    maf_df = pd.read_csv(df.loc[idx, 'phylogic_all_pairs_mut_ccfs'], sep='\t')
    #maf_df = pd.read_csv('~/Broad/JupyterReviewer/example_notebooks/example_data/all_mut_ccfs_maf_annotated_w_cnv_single_participant.txt', sep='\t')
    maf_cols_options = (list(maf_df))

    for col in default_maf_cols:
        if col in maf_cols_options and col not in maf_cols_value:
            maf_cols_value.append(col)

    for col in cols:
        if col in maf_cols_options and col not in maf_cols_value:
            maf_cols_value.append(col)

    for symbol in maf_df.Hugo_Symbol.unique():
        hugo_symbols.append(symbol)

    for classification in maf_df.Variant_Classification.unique():
        variant_classifications.append(classification)

    filtered_maf_df = maf_df.copy()
    if hugo:
        filtered_maf_df = filtered_maf_df[filtered_maf_df.Hugo_Symbol.isin(hugo)]
    if variant:
        filtered_maf_df = filtered_maf_df[filtered_maf_df.Variant_Classification.isin(variant)]
    if cluster:
        filtered_maf_df = filtered_maf_df[filtered_maf_df.Cluster_Assignment.isin(cluster)]

    return [
        maf_df,
        maf_cols_options,
        maf_cols_value,
        hugo_symbols,
        variant_classifications,
        filtered_maf_df
    ]

def gen_maf_table(df, idx, cols, hugo, table_size, variant, cluster, custom_colors):
    maf_df, maf_cols_options, maf_cols_value, hugo_symbols, variant_classifications, filtered_maf_df = gen_maf_columns(df, idx, cols, hugo, variant, cluster)

    return [
        maf_cols_options,
        maf_cols_value,
        dash_table.DataTable(
            data=filtered_maf_df.to_dict('records'),
            columns=[{'name': i, 'id': i, 'selectable': True} for i in maf_cols_value],
            filter_action='native',
            row_selectable='single',
            column_selectable='multi',
            page_action='native',
            page_current=0,
            page_size=table_size,
            style_data_conditional=gen_style_data_conditional(custom_colors)
        ),
        hugo_symbols,
        variant_classifications
    ]

def internal_gen_maf_table(df, idx, cols, hugo, table_size, variant, cluster, custom_colors):
    maf_df, maf_cols_options, maf_cols_value, hugo_symbols, variant_classifications, filtered_maf_df = gen_maf_columns(df, idx, cols, hugo, variant, cluster)

    return [
        maf_cols_options,
        cols,
        dash_table.DataTable(
                data=filtered_maf_df.to_dict('records'),
                columns=[{'name': i, 'id': i, 'selectable': True} for i in cols],
                filter_action='native',
                row_selectable='single',
                column_selectable='multi',
                page_action='native',
                page_current=0,
                page_size=table_size,
                style_data_conditional=gen_style_data_conditional(custom_colors)
        ),
        hugo_symbols,
        variant_classifications
    ]

def gen_ccf_plot(df, idx, time_scaled):
    if time_scaled:
        scatter_x = 'dfd'
        rect_x = 5
    else:
        scatter_x = 'order'
        rect_x = 6

    # random dict for now
    timing_data = {'17318_13_OCT_052219':	5, '17318_13_BB_111119': 10}

    cluster_ccfs = pd.read_csv('gs://fc-secure-c1d8f0c8-dc8c-418a-ac13-561b18de3d8e/1dc35867-4c57-487e-bcdd-e39820462211/phylogicndt/b007b77f-c150-490f-9d55-7ace9eb495dd/call-clustering/ONC106612.cluster_ccfs.txt', sep='\t')
    # cluster ccfs will eventually be the same format as mut ccfs
    mut_ccfs = pd.read_csv(df.loc[idx, 'phylogic_all_pairs_mut_ccfs'], sep='\t')
    cluster_df = cluster_ccfs[['Cluster_ID', 'Sample_ID', 'postDP_ccf_mean', 'postDP_ccf_CI_low', 'postDP_ccf_CI_high']].copy()

    cluster_df.loc[:, 'dfd'] = [int(timing_data[sample]) for sample in cluster_ccfs['Sample_ID']]
    samples_in_order = sorted(timing_data.keys(), key=lambda k: int(timing_data[k]))
    ordered_samples_dict = {s: o for s, o in zip(samples_in_order, np.arange(len(samples_in_order)))}
    cluster_df.loc[:, 'order'] = [ordered_samples_dict[s] for s in cluster_ccfs['Sample_ID']]

    mut_count_dict = mut_ccfs.drop_duplicates([
        'Patient_ID',
        'Hugo_Symbol',
        'Chromosome',
        'Start_position',
        'Cluster_Assignment'
    ]).groupby('Cluster_Assignment').count()['Patient_ID'].to_dict()

    cluster_colors = [cluster_color(i) for i in cluster_df['Cluster_ID'].unique()]
    cluster_df['Cluster_ID'] = cluster_df['Cluster_ID'].astype(str)

    fig = px.scatter(
        cluster_df,
        x=scatter_x,
        y='postDP_ccf_mean',
        color='Cluster_ID',
        color_discrete_sequence=cluster_colors
    )
    fig.update_traces(marker_size=15)

    for c, color in zip(cluster_df['Cluster_ID'].unique(), cluster_colors):
        this_cluster = cluster_df[cluster_df['Cluster_ID'] == c]
        for i in np.arange(this_cluster.shape[0] - 1):
            x = [this_cluster.iloc[i, rect_x], this_cluster.iloc[i + 1, rect_x], this_cluster.iloc[i + 1, rect_x],
                 this_cluster.iloc[i, rect_x], this_cluster.iloc[i, rect_x]]
            y = [this_cluster.iloc[i, 4], this_cluster.iloc[i + 1, 4], this_cluster.iloc[i + 1, 3],
                 this_cluster.iloc[i, 3], this_cluster.iloc[i, 4]]
            fig.add_trace(
                go.Scatter(x=x, y=y, fill="toself", fillcolor=color, line_color=color, opacity=0.4,
                           mode='none', showlegend=False))
            fig.add_shape(type="line", xref="x", yref="y",
                          x0=this_cluster.iloc[i, rect_x], x1=this_cluster.iloc[i + 1, rect_x],
                          y0=this_cluster.iloc[i, 2], y1=this_cluster.iloc[i + 1, 2],
                          line_width=min(mut_count_dict[int(c)], 15),
                          line_color=color, opacity=0.4, layer='below')
    fig.update_layout(plot_bgcolor='rgba(0,0,0,0)', height=600, width=900)
    fig.update_yaxes(title='ccf(x)', dtick=0.1, ticks='outside', showline=True, linecolor='black', range=[-0.03,1.05], showgrid=False)
    fig.update_xaxes(ticks='outside', showline=True, linecolor='black', showgrid=False)
    if time_scaled:
        fig.update_xaxes(title='Time (dfd)')
    else:
        fig.update_xaxes(title='Samples (timing - dfd)', tickvals=np.arange(len(samples_in_order)),
                         ticktext=[f'{s} ({timing_data[s]})' for s in samples_in_order])
    fig.data = fig.data[::-1]  # make the circles appear on top layer

    return [fig]

class PatientReviewer(ReviewerTemplate):

    def gen_review_data(
        self,
        review_data_fn: str,
        description: str='',
        df: pd.DataFrame = pd.DataFrame(),
        review_data_annotation_dict: {str: ReviewDataAnnotation} = {},
        reuse_existing_review_data_fn: str = None
    ):

        review_data_annotation_dict = {
            'purity': ReviewDataAnnotation('number', validate_input=validate_purity),
            'ploidy': ReviewDataAnnotation('number', validate_input=validate_ploidy),
            'mutation': ReviewDataAnnotation('text'),
            'class': ReviewDataAnnotation('radioitem', options=['Possible Driver', 'Likely Driver', 'Possible Artifact', 'Likely Artifact']),
            'description': ReviewDataAnnotation('text')
        }

        rd = ReviewData(
            review_data_fn=review_data_fn,
            description=description,
            df=df,
            review_data_annotation_dict = review_data_annotation_dict
        )

        return rd

    # list optional cols param
    def gen_review_app(self, custom_colors=[]) -> ReviewDataApp:
        app = ReviewDataApp()

        app.add_component(AppComponent(
            'Clinical Data',
            html.Div(
                dbc.Table.from_dataframe(df=pd.DataFrame()),
                id='clinical-data-component'
            ),
            callback_output=[Output('clinical-data-component', 'children')],
            new_data_callback=gen_clinical_data_table
        ), cols=['participant_id', 'gender', 'age_at_diagnosis', 'vital_status', 'death_date_dfd'])

        app.add_component(AppComponent(
            'Mutations',
            html.Div([
                html.Div([
                    dbc.Row([
                        dbc.Col([
                            html.P('Table Size (Rows)'),
                        ], width=2),
                        dbc.Col([
                            html.P('Select Columns')
                        ])
                    ]),
                    dbc.Row([
                        dbc.Col([
                            dcc.Dropdown(
                                options=[10,20,30],
                                value=10,
                                id='table-size-dropdown'
                            )
                        ], width=2),
                        dbc.Col([
                            dcc.Dropdown(
                                maf_cols_options,
                                maf_cols_value,
                                multi=True,
                                id='column-selection-dropdown'
                            )
                        ], width=10)
                    ])
                ]),

                html.Div(
                    dbc.Row([
                        dbc.Col([
                            dcc.Dropdown(
                                options=hugo_symbols,
                                multi=True,
                                placeholder='Filter by Hugo Symbol',
                                id='hugo-dropdown'
                            )
                        ], width=2),
                        dbc.Col([
                            dcc.Dropdown(
                                options=variant_classifications,
                                multi=True,
                                placeholder='Filter by Variant Classification',
                                id='variant-classification-dropdown'
                            )
                        ], width=2),
                        dbc.Col([
                            dcc.Dropdown(
                                options=cluster_assignments,
                                multi=True,
                                placeholder='Filter by Cluster Assignment',
                                id='cluster-assignment-dropdown'
                            )
                        ], width=2)
                    ])
                ),

                html.Div(dash_table.DataTable(
                    columns=[{'name': i, 'id': i, 'selectable': True} for i in pd.DataFrame().columns],
                    data=pd.DataFrame().to_dict('records'),
                    id='mutation-table'
                ), id='mutation-table-component'),
            ]),

            callback_input=[
                Input('column-selection-dropdown', 'value'),
                Input('hugo-dropdown', 'value'),
                Input('table-size-dropdown', 'value'),
                Input('variant-classification-dropdown', 'value'),
                Input('cluster-assignment-dropdown', 'value')
            ],
            callback_output=[
                Output('column-selection-dropdown', 'options'),
                Output('column-selection-dropdown', 'value'),
                Output('mutation-table-component', 'children'),
                Output('hugo-dropdown', 'options'),
                Output('variant-classification-dropdown', 'options')
            ],
            new_data_callback=gen_maf_table,
            internal_callback=internal_gen_maf_table
        ), custom_colors=custom_colors)

        app.add_component(AppComponent(
            'Phylogic Graphics',
            html.Div([
                html.Div(
                    dbc.Row([
                        dbc.Col([
                            dcc.Graph(
                                id='ccf-plot',
                                figure=px.scatter(pd.DataFrame())
                            )
                        ], width=8),
                        dbc.Col([
                            dcc.RadioItems(['Time Scaled', 'Not Time Scaled'], 'Time Scaled', id='time-scale-radio-item')
                        ], width=2)
                    ])
                )
            ]),

            callback_input=[Input('time-scale-radio-item', 'value')],
            callback_output=[Output('ccf-plot', 'figure')],
            new_data_callback=gen_ccf_plot,
            internal_callback=gen_ccf_plot
        ))

        app.add_component(AppComponent(
            'Purity Slider',
            html.Div(dcc.Slider(0, 1, 0.1, value=0.5, id='a-slider')),
            callback_output=[Output('a-slider', 'value')],
            callback_states_for_autofill=[State('a-slider', 'value')]
        ))

        return app

    def gen_autofill(self):
        self.add_autofill('Purity Slider', {'purity': State('a-slider', 'value')})