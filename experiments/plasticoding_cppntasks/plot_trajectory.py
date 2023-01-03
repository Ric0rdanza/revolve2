from revolve2.core.optimization.ea.generic_ea import DbEAOptimizerGeneration, \
    DbEAOptimizerIndividual, DbEAOptimizer, DbEnvconditions
import argparse
from revolve2.core.database.serializers import DbStates
from sqlalchemy.ext.asyncio.session import AsyncSession
import pandas
import matplotlib.pyplot as plt
import seaborn as sb
from statannot import add_stat_annotation
import pprint
import sys
import os
import asyncio
from revolve2.core.database import open_async_database_sqlite
from sqlalchemy.future import select
from revolve2.core.optimization.ea.generic_ea import DbEnvconditions
from ast import literal_eval

#parser = argparse.ArgumentParser()
#parser.add_argument("study")
#parser.add_argument("experiments")
#parser.add_argument("runs")
#parser.add_argument("final_gen")
#parser.add_argument("comparison")
#parser.add_argument("mainpath")
#args = parser.parse_args()

study = "plasticoding_cppntasks"
experiments_name = ["tilted", "rugged"]
runs = list(range(1, 8 + 1))
final_gen = 200
#comparison = args.comparison
mainpath = "ec22zhengtianshi"
bests = 1
env_conditions = 2

experiments = experiments_name
# non plasticc and plastic
clrs = ['#404040', '#00CCCC']

pandas.set_option('display.max_rows', None)


async def main() -> None:

    for idexp, exp in enumerate(experiments):
        print(exp)

        font = {'font.size': 20}
        plt.rcParams.update(font)
        fig, ax = plt.subplots()
        plt.xlabel('')
        plt.ylabel('')

        ax.set_ylim(-0.9, 2.2)
        ax.set_xlim(-2, 2.2)
        ax.invert_yaxis()

        for run in runs:
            db = open_async_database_sqlite(f'/home/chen/Documents/storage/{mainpath}/{study}/{exp}/run_{run}')

            async with AsyncSession(db) as session:
                query = select(DbEAOptimizerGeneration, DbEAOptimizerIndividual, DbStates) \
                    .filter((DbEAOptimizerGeneration.individual_id == DbEAOptimizerIndividual.individual_id)
                            & (DbStates.id == DbEAOptimizerIndividual.states_id)
                            & (DbEAOptimizerGeneration.env_conditions_id == DbEAOptimizerIndividual.env_conditions_id)
                            & (DbEAOptimizerGeneration.generation_index == final_gen)
                            )

                if exp in ['nonplasticforthright', 'plasticforthright', 'fullplasticforthright']:
                    query = query.order_by(
                        DbEAOptimizerGeneration.forthright_dominated.desc(),
                        DbEAOptimizerGeneration.individual_id.asc())
                if exp in ['nonplasticbackforth', 'plasticbackforth', 'fullplasticbackforth']:
                    query = query.order_by(
                        DbEAOptimizerGeneration.backforth_dominated.desc(),
                        DbEAOptimizerGeneration.individual_id.asc())

                rows = ((await session.execute(query)).all())

                num_lines = bests * env_conditions
                for idx, c_row in enumerate(rows[0:num_lines]):

                    positions = []
                    individual_id = c_row.DbEAOptimizerIndividual.individual_id
                    cond = c_row.DbEAOptimizerIndividual.env_conditions_id
                    states = literal_eval(c_row.DbStates.serialized_states)

                    for s in states:
                        positions.append([exp, run, individual_id, cond, s,
                                          states[s]['position'][0], states[s]['position'][1]])
                    positions = pandas.DataFrame(positions,
                                                 columns=['exp', 'run', 'individual_id', 'cond', 'step', 'x', 'y'])

                   # pprint.pprint(positions)

                    # x and y are intentionally inverted, because of isaacs visuals
                    ax.plot(positions['y'], positions['x'], alpha=0.7,  label=f'...', c=clrs[cond-1])

        plt.savefig(f'/home/chen/Documents/storage/{mainpath}/{study}/analysis/traj_{exp}.png')
        plt.clf()
        plt.close(fig)

if __name__ == "__main__":
    asyncio.run(main())






















