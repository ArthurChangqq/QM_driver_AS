from OnMachine.Octave_Config.QM_config_dynamic import Circuit_info, QM_config
from OnMachine.MeasFlow.ConfigBuildUp import spec_loca, config_loca
import numpy as np
spec = Circuit_info(q_num=4)
config = QM_config()
spec.import_spec(spec_loca)
config.import_config(config_loca)

if __name__ == '__main__':
    mssn_cata = input("CS, power or flux?")

    match mssn_cata.lower():
        case "cs":
            # Update RO IF after Cavity Search
            # [target_q, IF(MHz)]
            new_LO = 5.96
            cavities = [['q1',-238],['q2',54],['q3',-124],['q4',141]]
            for i in cavities:
                f = spec.update_RoInfo_for(target_q=i[0],LO=new_LO,IF=i[1])
                config.update_ReadoutFreqs(f)
            # print(config.get_config()['mixers'])
            spec.export_spec(spec_loca)
            config.export_config(config_loca)

        case "power":
            # Update RO amp, dress RO after power dependence
            # [target_q, amp_scale, added_IF(MHz)]        
            modifiers = [['q1',0.2,0],['q2',0.2,0.39],['q3',0.2,0],['q4',0.15,0.2]] 
            for i in modifiers:
                old_if = spec.get_spec_forConfig("ro")[i[0]]["resonator_IF"]*1e-6
                old_amp = spec.get_spec_forConfig("ro")[i[0]]["readout_amp"]
                config.update_ReadoutFreqs(spec.update_RoInfo_for(target_q=i[0],IF=i[2]+old_if))
                spec.update_RoInfo_for(i[0],amp=old_amp*i[1])
                config.update_Readout(i[0],spec.get_spec_forConfig('ro'))

            spec.export_spec(spec_loca)
            config.export_config(config_loca)
        
        case "rf":
            # Update RO amp, dress RO after power dependence
            # [target_q, offset_bias, added_IF(MHz)]        
            modifiers = [['q1',0,-0.1],['q2',-0.04,0],['q3',-0.04,0],['q4',-0.04,0]] 
            for i in modifiers:
                old_if = spec.get_spec_forConfig("ro")[i[0]]["resonator_IF"]*1e-6
                config.update_ReadoutFreqs(spec.update_RoInfo_for(target_q=i[0],IF=i[2]+old_if))
                z = spec.update_ZInfo_for(target_q=i[0],offset=i[1])
                config.update_z_offset(z,mode='offset')
            
            spec.export_spec(spec_loca)
            config.export_config(config_loca)

        case "q":
            # Update RO amp, dress RO after power dependence
            # [target_q, offset_bias, Q freq(GHz), LO(MHz)]        
            modifiers = [['q1',0,3.6,3.5],['q2',-0.04,4.2,4],['q3',-0.04,3.2535,3.1],['q4',-0.04,3.1,3.10]] 
            for i in modifiers:
                ref_IF = (i[2]-i[3])*1000
                if np.abs(ref_IF) > 350:
                    print("Warning IF > +/-350 MHz, IF is set 350 MHz")
                    ref_IF = np.sign(ref_IF)*350
                config.update_controlFreq(spec.update_aXyInfo_for(target_q=i[0],IF=ref_IF,LO=i[3]))
                z = spec.update_ZInfo_for(target_q=i[0],offset=i[1])
                config.update_z_offset(z,mode='offset')
            
            spec.export_spec(spec_loca)
            config.export_config(config_loca)

        case _:
            print("No such CMD")
            pass
